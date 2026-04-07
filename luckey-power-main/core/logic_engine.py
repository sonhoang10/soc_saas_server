from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import json
import datetime
import re
import time
from dotenv import load_dotenv
import os

app = FastAPI()

# ================= CẤU HÌNH CORS =================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= CẤU HÌNH HỆ THỐNG =================
load_dotenv(dotenv_path="../.env") # Load file .env từ thư mục gốc

WEB_BACKEND_URL = "http://localhost:8000/api/alerts" 
KAFKA_IP = os.getenv("KAFKA_IP")
BAN_HISTORY_FILE = "banned_ips_history.txt"

TIME_WINDOW_SECONDS = 60  
MAX_FAILURES = 5          

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

# ================= HÀM HỖ TRỢ =================
def load_banned_ips():
    if not os.path.exists(BAN_HISTORY_FILE): return
    with open(BAN_HISTORY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.split("|")
            if len(parts) >= 3: 
                blocked_ips.add((parts[1].strip(), parts[2].strip()))
    print(f"[*] Đã nạp {len(blocked_ips)} IP từ lịch sử ban.")

load_banned_ips()

def extract_target_ip(log_data):
    try:
        host_info = log_data.get("host", {})
        host_ips = host_info.get("ip", [])
        if not host_ips: return "Unknown"
        if isinstance(host_ips, str): host_ips = [host_ips]
        
        fallback_ip = None
            
        for ip in host_ips:
            ip = str(ip).strip()
            if ":" in ip: continue 
            is_private = ip.startswith((
                "10.", "192.168.", "127.",
                "172.16.", "172.17.", "172.18.", "172.19.", "172.20.", 
                "172.21.", "172.22.", "172.23.", "172.24.", "172.25.", 
                "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31."
            ))
            if not is_private:
                return ip
            else:
                if fallback_ip is None:
                    fallback_ip = ip
                
        return fallback_ip if fallback_ip else "Unknown"
    except Exception as e:
        return "Unknown"

def check_brute_force_threshold(ip: str) -> bool:
    if ip == "Unknown" or not ip: return False
    current_time = time.time()
    if ip not in violation_history: violation_history[ip] = []
    violation_history[ip].append(current_time)
    violation_history[ip] = [t for t in violation_history[ip] if current_time - t <= TIME_WINDOW_SECONDS]
    
    if len(violation_history[ip]) >= MAX_FAILURES:
        violation_history[ip] = [] 
        return True
    return False

# ================= HÀNH ĐỘNG PHÒNG THỦ =================
def block_ip_action(attacker_ip: str, reason: str, target_server_ip: str):
    if target_server_ip == "Unknown" or not target_server_ip:
        print(f"[-] HỦY LỆNH BAN {attacker_ip}: IP Server Nạn Nhân không hợp lệ.")
        return

    if (attacker_ip, target_server_ip) in blocked_ips or attacker_ip in [KAFKA_IP, "127.0.0.1", "Unknown"]: 
        return
        
    print(f"[*] GỌI AGENT: Chặn {attacker_ip} trên {target_server_ip} (Lý do: {reason})")
    try:
        agent_url = f"http://{target_server_ip}:8001/agent/ban"
        response = requests.post(agent_url, json={"ip": attacker_ip}, timeout=5)
        
        if response.status_code == 200:
            blocked_ips.add((attacker_ip, target_server_ip))
            now = (datetime.datetime.now() + datetime.timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")
            with open(BAN_HISTORY_FILE, "a", encoding="utf-8") as f:
                f.write(f"{now} | {attacker_ip} | {target_server_ip} | {reason}\n")
            print(f"[+] BAN THÀNH CÔNG: {attacker_ip}")
        else:
            print(f"[-] AGENT TỪ CHỐI: {response.text}")
    except Exception as e: 
        print(f"[-] LỖI KẾT NỐI AGENT {target_server_ip}: {e}")

def unblock_ip_action(attacker_ip: str, target_server_ip: str):
    if target_server_ip == "Unknown" or not target_server_ip:
        return

    if (attacker_ip, target_server_ip) not in blocked_ips: return
    
    print(f"[*] GỌI AGENT: Mở khóa {attacker_ip} trên {target_server_ip}")
    try:
        agent_url = f"http://{target_server_ip}:8001/agent/unban"
        response = requests.post(agent_url, json={"ip": attacker_ip}, timeout=5)
        
        if response.status_code == 200:
            blocked_ips.remove((attacker_ip, target_server_ip))
            if os.path.exists(BAN_HISTORY_FILE):
                with open(BAN_HISTORY_FILE, "r") as f: lines = f.readlines()
                with open(BAN_HISTORY_FILE, "w") as f:
                    for line in lines:
                        if f"| {attacker_ip} | {target_server_ip} |" not in line: 
                            f.write(line)
            print(f"[+] UNBAN THÀNH CÔNG: {attacker_ip}")
    except Exception as e: 
        print(f"[-] LỖI KẾT NỐI AGENT: {e}")

# ================= API ENDPOINTS =================
class RawLogPayload(BaseModel): raw_data: str
class IPPayload(BaseModel): 
    ip: str
    target_server_ip: str
    reason: str = "Manual Ban from Dashboard"
class AutoBanPayload(BaseModel): enabled: bool

@app.get("/api/autoban/status")
def get_autoban_status(): return {"enabled": auto_ban_enabled}

@app.post("/api/autoban/toggle")
def toggle_autoban(payload: AutoBanPayload):
    global auto_ban_enabled
    auto_ban_enabled = payload.enabled
    return {"message": "Success", "enabled": auto_ban_enabled}

@app.post("/api/analyze")
async def analyze_log(payload: RawLogPayload, bg_tasks: BackgroundTasks):
    try:
        log_data = json.loads(payload.raw_data)
        message = log_data.get("message", "")
        log_type = log_data.get("fields", {}).get("log_type", "")
        target_server_ip = extract_target_ip(log_data)
        
        alert_payload = None
        now_str = (datetime.datetime.now() + datetime.timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")

        if log_type == "os_ssh_auth" and "Failed password" in message:
            ip_match = re.search(r'from (\d+\.\d+\.\d+\.\d+)', message)
            attacker_ip = ip_match.group(1) if ip_match else "Unknown"
            
            if check_brute_force_threshold(attacker_ip):
                action_text = "(Đã tự động Ban)" if auto_ban_enabled else "(Chờ Admin)"
                if auto_ban_enabled: bg_tasks.add_task(block_ip_action, attacker_ip, "Brute-force SSH", target_server_ip)
                
                alert_payload = {
                    "time": now_str, "level": "Critical", "type": "Brute-force SSH", 
                    "ip": attacker_ip, 
                    "target_ip": target_server_ip,
                    "target_server": target_server_ip, 
                    "server": target_server_ip,        
                    "analysis": f"🚨 SSH: IP {attacker_ip} sai {MAX_FAILURES} lần. {action_text}"
                }

        elif log_type == "web_app_login":
            app_data = log_data.get("app_data", {})
            attacker_ip = app_data.get("ip", "Unknown").replace("::ffff:", "")
            action = app_data.get("action", "")
            username = str(app_data.get("username", ""))
            password = str(app_data.get("password_tried", "")) # Đã sửa: Lấy mật khẩu

            # Đã sửa: Kiểm tra Regex trên cả Username VÀ Password
            if SQLI_PATTERN.search(username) or SQLI_PATTERN.search(password):
                action_text = "(Đã tự động Ban)" if auto_ban_enabled else "(Chờ Admin)"
                if auto_ban_enabled: bg_tasks.add_task(block_ip_action, attacker_ip, "SQL Injection Web", target_server_ip)
                
                alert_payload = {
                    "time": now_str, "level": "Critical", "type": "SQL Injection Web", 
                    "ip": attacker_ip, 
                    "target_ip": target_server_ip,
                    "target_server": target_server_ip, 
                    "server": target_server_ip,        
                    "analysis": f"🔥 SQLi: IP {attacker_ip} tấn công qua User/Pass. {action_text}"
                }
            
            elif action == "login_failed":
                if check_brute_force_threshold(attacker_ip):
                    action_text = "(Đã tự động Ban)" if auto_ban_enabled else "(Chờ Admin)"
                    if auto_ban_enabled: bg_tasks.add_task(block_ip_action, attacker_ip, "Brute-force Web App", target_server_ip)
                    
                    alert_payload = {
                        "time": now_str, "level": "Critical", "type": "Brute-force Web App", 
                        "ip": attacker_ip, 
                        "target_ip": target_server_ip,
                        "target_server": target_server_ip, 
                        "server": target_server_ip,        
                        "analysis": f"🚨 Web: IP {attacker_ip} sai {MAX_FAILURES} lần. {action_text}"
                    }

        if alert_payload:
            requests.post(WEB_BACKEND_URL, json=alert_payload)
            return {"status": "Alert triggered"}
            
        return {"status": "Normal"}
    except Exception as e: 
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
    return {"message": "Lệnh Ban đã được gửi"}

@app.post("/api/unban")
def manual_unban(payload: IPPayload, bg_tasks: BackgroundTasks):
    bg_tasks.add_task(unblock_ip_action, payload.ip, payload.target_server_ip)
    return {"message": "Lệnh Unban đã được gửi"}