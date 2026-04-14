from kafka import KafkaConsumer
import requests
import json
import re
import os
import logging
import time
from dotenv import load_dotenv

# ================= CẤU HÌNH LOGGING=================
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================= ĐỌC BIẾN MÔI TRƯỜNG =================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

MAIN_SERVER = os.getenv("MAIN_SERVER", "127.0.0.1")
LOGIC_ENGINE_URL = f"http://{MAIN_SERVER}:8001/api/analyze"

CH_HOST = os.getenv("CH_HOST", "127.0.0.1")
CH_PORT = os.getenv("CH_PORT", "8123")
CLICKHOUSE_URL = f"http://{CH_HOST}:{CH_PORT}/"
DB_NAME = "soc_db"

CH_USER = os.getenv("CH_USER", "default")
CH_PASS = os.getenv("CH_PASS", "") 

KAFKA_SERVER = os.getenv("KAFKA_SERVER", "127.0.0.1")
KAFKA_PORT = os.getenv("KAFKA_PORT", "9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "soc-raw-logs")




# ================= CẤU HÌNH BATCHING =================
BATCH_SIZE = 1000      
BATCH_TIMEOUT = 5.0    

http_session = requests.Session()
if CH_PASS:
    http_session.auth = (CH_USER, CH_PASS)
try:
    consumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=[f'{KAFKA_SERVER}:{KAFKA_PORT}'],
        group_id='soc-log-processors',
        api_version=(3, 0, 0),
        auto_offset_reset='earliest', # Nên dùng earliest để không bỏ lỡ log khi code sập
        enable_auto_commit=False,     # TẮT AUTO COMMIT -> Tự quản lý để chống mất data
        value_deserializer=lambda x: x.decode('utf-8', errors='ignore')
    )
    logger.info("✅ [NORMALIZER] Đã kết nối Kafka thành công.")
except Exception as e:
    logger.error(f"❌ Không thể kết nối tới Kafka: {e}")
    exit(1)

# ================= LOGIC XỬ LÝ =================
def normalize_log(raw_log):
    try:
        data = json.loads(raw_log)
        clean_data = {
            "timestamp": data.get("@timestamp", ""),
            "target_ip": "",
            "log_type": data.get("fields", {}).get("log_type", "unknown"),
            "action": "unknown",
            "username": "",
            "raw_data": raw_log
        }

        if clean_data["log_type"] == "web_app_login":
            app_data = data.get("app_data", {})
            clean_data["target_ip"] = app_data.get("ip", "").replace("::ffff:", "")
            clean_data["action"] = app_data.get("action", "unknown")
            clean_data["username"] = app_data.get("username", "")

        elif clean_data["log_type"] == "os_ssh_auth":
            message = data.get("message", "")
            ip_match = re.search(r'from (\d+\.\d+\.\d+\.\d+)', message)
            if ip_match:
                clean_data["target_ip"] = ip_match.group(1)
            
            if "Failed password" in message:
                clean_data["action"] = "ssh_failed_login"
            elif "Invalid user" in message:
                clean_data["action"] = "ssh_invalid_user"
                
            user_match = re.search(r'invalid user (\S+)', message)
            if user_match:
                clean_data["username"] = user_match.group(1)

        return clean_data
    except json.JSONDecodeError:
        logger.warning("⚠️ Lỗi Parse JSON: Log không đúng định dạng.")
        return None
    except Exception as e:
        logger.error(f"❌ Lỗi xử lý log: {e}")
        return None

# ================= VÒNG LẶP CHÍNH (CHUẨN BATCHING) =================
clickhouse_batch = []
last_flush_time = time.time()

def flush_to_clickhouse(batch):
    if not batch:
        return True
    
    # ClickHouse JSONEachRow yêu cầu data là chuỗi các object JSON nối nhau bằng \n
    # Hoặc đơn giản là gửi 1 string có chứa nhiều dòng JSON
    payload = "\n".join(json.dumps(log) for log in batch)
    
    try:
        query = "INSERT INTO raw_logs FORMAT JSONEachRow"
        response = http_session.post(
            CLICKHOUSE_URL, 
            params={"query": query, "database": DB_NAME}, 
            data=payload,
            timeout=5
        )
        if response.status_code == 200:
            logger.info(f"💾 Đã lưu thành công {len(batch)} logs vào ClickHouse.")
            return True
        else:
            logger.error(f"⚠️ ClickHouse từ chối data ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Lỗi mạng khi gửi tới ClickHouse: {e}")
        return False

try:
    for message in consumer:
        raw_log = message.value
        clean_json = normalize_log(raw_log)
        
        if clean_json and clean_json["target_ip"]:
            # 1. GỬI SANG LOGIC ENGINE (Vẫn gửi real-time từng log hoặc có thể batch sau)
            try:
                http_session.post(LOGIC_ENGINE_URL, json=clean_json, timeout=1)
            except Exception as e:
                logger.warning(f"⚠️ Cảnh báo gửi Logic Engine chậm: {e}")

            # Chuẩn bị data cho ClickHouse
            clickhouse_data = clean_json.copy()
            if clickhouse_data["timestamp"]:
                clickhouse_data["timestamp"] = clickhouse_data["timestamp"].replace("T", " ")[:19]
            
            clickhouse_batch.append(clickhouse_data)

        # 2. KIỂM TRA ĐIỀU KIỆN FLUSH BATCH
        current_time = time.time()
        if len(clickhouse_batch) >= BATCH_SIZE or (current_time - last_flush_time >= BATCH_TIMEOUT and len(clickhouse_batch) > 0):
            
            # Gửi lên DB
            success = flush_to_clickhouse(clickhouse_batch)
            
            if success:
                # NẾU THÀNH CÔNG -> Xác nhận với Kafka là đã xử lý xong tới message này
                consumer.commit()
                clickhouse_batch.clear()
                last_flush_time = time.time()
            else:
                # NẾU LỖI -> Tùy business logic: Có thể sleep(5) rồi gửi lại, hoặc ghi ra file Dead Letter.
                # Ở đây ví dụ chờ 2 giây rồi vòng lặp sau sẽ thử lại (batch chưa bị clear)
                logger.error("🛑 Gửi ClickHouse thất bại, sẽ thử lại...")
                time.sleep(2) 

except KeyboardInterrupt:
    logger.info("🛑 Đang đóng Kafka Consumer an toàn...")
    # Cố gắng flush nốt những log cuối cùng trong mảng trước khi tắt
    if clickhouse_batch:
        logger.info("Flush nốt batch cuối trước khi tắt...")
        if flush_to_clickhouse(clickhouse_batch):
            consumer.commit()
    consumer.close()