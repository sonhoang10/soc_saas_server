import os
import re
import json
import time
import logging
import datetime
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# ================= CẤU HÌNH LOGGING =================
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - [%(levelname)s] - %(message)s'
)
logger = logging.getLogger(__name__)

# ================= ĐỌC BIẾN MÔI TRƯỜNG =================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

WEB_BACKEND_URL = os.getenv("WEB_BACKEND_URL", "http://localhost:8000/api/alerts")
AGENT_PORT = os.getenv("AGENT_PORT", "8001")
WHITELIST_IPS = os.getenv("WHITELIST_IPS", "127.0.0.1,143.198.82.147").split(",")
BAN_HISTORY_FILE = os.path.join(BASE_DIR, os.getenv("BAN_HISTORY_FILE", "banned_ips_history.txt"))

TIME_WINDOW_SECONDS = int(os.getenv("TIME_WINDOW_SECONDS", 60))
MAX_FAILURES = int(os.getenv("MAX_FAILURES", 5))

# ================= STATE & REGEX =================
violation_history = {} 
blocked_ips = set() 
auto_ban_enabled = False 

SQLI_PATTERN = re.compile(
    r"(?i)" 
    r"(\b(OR|AND|WHERE|HAVING)\b|\|\||&&)\s*(.?\w+.?\s*(=|>|<|>=|<=|LIKE)\s*.?\w+.?|\d+\s*(=|>|<|>=|<=)\s*\d+)|"
    r"(\b(UNION\s+SELECT|SELECT\s+.*|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|DROP\s+(TABLE|DATABASE)|ALTER\s+TABLE)\b)|"
    r"(\b(information_schema|mysql\.user|sys\.tables|pg_shadow)\b)|"
    r"(\b(WAITFOR\s+DELAY|SLEEP\(|BENCHMARK\()\b)|"
    r"(--|–|—|#|/\*.*\*/)"
)

# ================= LIFESPAN (Khởi động & Dọn dẹp) =================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Khởi chạy: Load lịch sử ban IP
    if os.path.exists(BAN_HISTORY_FILE):
        with open(BAN_HISTORY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.split("|")
                if len(parts) >= 3: 
                    blocked_ips.add((parts[1].strip(), parts[2].strip()))
        logger.info(f"✅ Đã nạp {len(blocked_ips)} IP từ lịch sử ban.")
    
    # Cấu hình httpx client dùng chung (tối ưu TCP Connection)
    app.state.http_client = httpx.AsyncClient()
    yield
    # Dọn dẹp khi tắt App
    await app.state.http_client.aclose()
    logger.info("🛑 Đã đóng HTTP Client an toàn.")

app = FastAPI(lifespan=lifespan)

# ================= CẤU HÌNH CORS =================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= HÀM HỖ TRỢ =================
def extract_target_ip(log_data):
    """Trích xuất IP Server nạn nhân. Trả về Unknown nếu không thấy."""
    try:
        host_info = log_data.get("host", {})
        host_ips = host_info.get("ip", [])
        if not host_ips: return "Unknown"
        if isinstance(host_ips, str): host_ips = [host_ips]
        
        fallback_ip = None
        for ip in host_ips:
            ip = str(ip).strip()
            if ":" in ip: continue  # Bỏ qua IPv6
            is_private = ip.startswith((
                "10.", "192.168.", "127.",
                "172.16.", "172.17.", "172.18.", "172.19.", "172.20.", 
                "172.21.", "172.22.", "172.23.", "172.24.", "172.25.", 
                "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31."
            ))
            if not is_private: return ip
            if fallback_ip is None: fallback_ip = ip
                
        return fallback_ip if fallback_ip else "Unknown"
    except Exception:
        return "Unknown"

def check_brute_force_threshold(ip: str) -> bool:
    if ip == "Unknown" or not ip: return False
    current_time = time.time()
    
    # Fix Memory Leak cơ bản
    if len(violation_history) > 10000:
        keys_to_delete = [k for k, v in violation_history.items() if current_time - v[-1] > TIME_WINDOW_SECONDS]
        for k in keys_to_delete: del violation_history[k]

    if ip not in violation_history: violation_history[ip] = []
    
    violation_history[ip].append(current_time)
    violation_history[ip] = [t for t in violation_history[ip] if current_time - t <= TIME_WINDOW_SECONDS]
    
    # --- ĐÃ SỬA: CHỈ TRẢ VỀ TRUE 1 LẦN DUY NHẤT KHI CHẠM MỐC ---
    if len(violation_history[ip]) == MAX_FAILURES:
        return True
    elif len(violation_history[ip]) > MAX_FAILURES:
        return False
        
    return False

# ================= HÀNH ĐỘNG PHÒNG THỦ (ASYNC) =================
async def block_ip_action(attacker_ip: str, reason: str, target_server_ip: str):
    if target_server_ip == "Unknown" or not target_server_ip:
        logger.warning(f"⚠️ Hủy lệnh Ban {attacker_ip}: IP Server Nạn Nhân không hợp lệ.")
        return

    if (attacker_ip, target_server_ip) in blocked_ips or attacker_ip in WHITELIST_IPS: 
        return
        
    logger.info(f"🚀 GỌI AGENT: Chặn {attacker_ip} trên {target_server_ip} (Lý do: {reason})")
    try:
        agent_url = f"http://{target_server_ip}:{AGENT_PORT}/agent/ban"
        response = await app.state.http_client.post(agent_url, json={"ip": attacker_ip}, timeout=5.0)
        
        if response.status_code == 200:
            blocked_ips.add((attacker_ip, target_server_ip))
            now = (datetime.datetime.now() + datetime.timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")
            with open(BAN_HISTORY_FILE, "a", encoding="utf-8") as f:
                f.write(f"{now} | {attacker_ip} | {target_server_ip} | {reason}\n")
            logger.info(f"✅ BAN THÀNH CÔNG: {attacker_ip}")
        else:
            logger.error(f"❌ AGENT TỪ CHỐI BAN: {response.text}")
    except Exception as e: 
        logger.error(f"❌ LỖI KẾT NỐI AGENT {target_server_ip}: {e}")

async def unblock_ip_action(attacker_ip: str, target_server_ip: str):
    if target_server_ip == "Unknown" or not target_server_ip: return
    if (attacker_ip, target_server_ip) not in blocked_ips: return
    
    logger.info(f"🔓 GỌI AGENT: Mở khóa {attacker_ip} trên {target_server_ip}")
    try:
        agent_url = f"http://{target_server_ip}:{AGENT_PORT}/agent/unban"
        response = await app.state.http_client.post(agent_url, json={"ip": attacker_ip}, timeout=5.0)
        
        if response.status_code == 200:
            blocked_ips.remove((attacker_ip, target_server_ip))
            if os.path.exists(BAN_HISTORY_FILE):
                with open(BAN_HISTORY_FILE, "r") as f: lines = f.readlines()
                with open(BAN_HISTORY_FILE, "w") as f:
                    for line in lines:
                        if f"| {attacker_ip} | {target_server_ip} |" not in line: 
                            f.write(line)
            logger.info(f"✅ UNBAN THÀNH CÔNG: {attacker_ip}")
    except Exception as e: 
        logger.error(f"❌ LỖI KẾT NỐI AGENT UNBAN: {e}")

# ================= API ENDPOINTS =================
class CleanLogPayload(BaseModel):
    timestamp: str
    target_ip: str 
    log_type: str
    action: str
    username: str
    raw_data: str 

class IPPayload(BaseModel): 
    ip: str
    target_server_ip: str
    reason: str = "Manual Ban from Dashboard"

class AutoBanPayload(BaseModel): 
    enabled: bool

@app.get("/api/autoban/status")
def get_autoban_status(): 
    return {"enabled": auto_ban_enabled}

@app.post("/api/autoban/toggle")
def toggle_autoban(payload: AutoBanPayload):
    global auto_ban_enabled
    auto_ban_enabled = payload.enabled
    logger.info(f"⚙️ Auto-ban status changed: {auto_ban_enabled}")
    return {"message": "Success", "enabled": auto_ban_enabled}

@app.post("/api/analyze")
async def analyze_log(payload: CleanLogPayload, bg_tasks: BackgroundTasks):
    try:
        attacker_ip = payload.target_ip
        if not attacker_ip or attacker_ip == "Unknown":
            return {"status": "Ignored: No Attacker IP"}

        log_data = json.loads(payload.raw_data)
        victim_server_ip = extract_target_ip(log_data)

        # --- ĐÃ SỬA: CHẶN LOGS TỪ IP ĐÃ BỊ BAN TỪ VÒNG GỬI XE ---
        if (attacker_ip, victim_server_ip) in blocked_ips:
            return {"status": "Ignored: IP already blocked"}

        alert_payload = None
        now_str = (datetime.datetime.now() + datetime.timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")

        # 1. Phát hiện Brute-force SSH
        if payload.log_type == "os_ssh_auth" and payload.action in ["ssh_failed_login", "ssh_invalid_user"]:
            if check_brute_force_threshold(attacker_ip):
                action_text = "(Đã tự động Ban)" if auto_ban_enabled else "(Chờ Admin)"
                if auto_ban_enabled: 
                    bg_tasks.add_task(block_ip_action, attacker_ip, "Brute-force SSH", victim_server_ip)
                
                alert_payload = {
                    "time": now_str, "level": "Critical", "type": "Brute-force SSH", 
                    "ip": attacker_ip, "target_server": victim_server_ip, "server": victim_server_ip,        
                    "analysis": f"🚨 SSH: IP {attacker_ip} sai {MAX_FAILURES} lần. {action_text}"
                }

        # 2. Phát hiện Tấn công Web App
        elif payload.log_type == "web_app_login":
            app_data = log_data.get("app_data", {})
            password = str(app_data.get("password_tried", "")) 

            # Check SQLi
            if SQLI_PATTERN.search(payload.username) or SQLI_PATTERN.search(password):
                action_text = "(Đã tự động Ban)" if auto_ban_enabled else "(Chờ Admin)"
                if auto_ban_enabled: 
                    bg_tasks.add_task(block_ip_action, attacker_ip, "SQL Injection Web", victim_server_ip)
                
                alert_payload = {
                    "time": now_str, "level": "Critical", "type": "SQL Injection Web", 
                    "ip": attacker_ip, "target_server": victim_server_ip, "server": victim_server_ip,        
                    "analysis": f"🔥 SQLi: IP {attacker_ip} tấn công qua User/Pass. {action_text}"
                }
            
            # Check Brute-force Web
            elif payload.action == "login_failed":
                if check_brute_force_threshold(attacker_ip):
                    action_text = "(Đã tự động Ban)" if auto_ban_enabled else "(Chờ Admin)"
                    if auto_ban_enabled: 
                        bg_tasks.add_task(block_ip_action, attacker_ip, "Brute-force Web App", victim_server_ip)
                    
                    alert_payload = {
                        "time": now_str, "level": "Critical", "type": "Brute-force Web App", 
                        "ip": attacker_ip, "target_server": victim_server_ip, "server": victim_server_ip,        
                        "analysis": f"🚨 Web: IP {attacker_ip} sai {MAX_FAILURES} lần. {action_text}"
                    }

        # Bắn Alert về Web Backend (Sử dụng Async HTTP)
        if alert_payload:
            bg_tasks.add_task(app.state.http_client.post, WEB_BACKEND_URL, json=alert_payload)
            return {"status": "Alert triggered"}
            
        return {"status": "Normal"}
    except Exception as e: 
        logger.error(f"❌ Lỗi nội bộ Analyze Log: {e}")
        return {"status": "Error", "details": str(e)}

@app.get("/api/banned_ips")
def get_banned_ips():
    ips = []
    if os.path.exists(BAN_HISTORY_FILE):
        with open(BAN_HISTORY_FILE, "r") as f:
            for line in f:
                parts = line.split("|")
                if len(parts) >= 4:
                    ips.append({
                        "time": parts[0].strip(), "ip": parts[1].strip(), 
                        "target_server": parts[2].strip(), "reason": parts[3].strip()
                    })
    return {"banned": ips[::-1]} 

@app.post("/api/ban")
def manual_ban(payload: IPPayload, bg_tasks: BackgroundTasks):
    bg_tasks.add_task(block_ip_action, payload.ip, payload.reason, payload.target_server_ip)
    return {"message": "Lệnh Ban đã được gửi vào hàng đợi xử lý nền"}

@app.post("/api/unban")
def manual_unban(payload: IPPayload, bg_tasks: BackgroundTasks):
    bg_tasks.add_task(unblock_ip_action, payload.ip, payload.target_server_ip)
    return {"message": "Lệnh Unban đã được gửi vào hàng đợi xử lý nền"}