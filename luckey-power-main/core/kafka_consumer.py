from kafka import KafkaConsumer
import requests
import json
import os
from dotenv import load_dotenv

# Load cấu hình từ file .env ở thư mục gốc
load_dotenv(dotenv_path="../.env")
KAFKA_IP = os.getenv("KAFKA_IP")
LOGIC_ENGINE_URL = "http://localhost:8001/api/analyze"

consumer = KafkaConsumer(
    'soc-raw-logs',
    bootstrap_servers=[f'{KAFKA_IP}:9092'], 
    api_version=(3, 0, 0),
    auto_offset_reset='latest',
    enable_auto_commit=True,
    value_deserializer=lambda x: x.decode('utf-8')
)

print(f"✅ [CONSUMER] Đã kết nối Kafka {KAFKA_IP}. Đang hút log...")

for message in consumer:
    raw_log = message.value
    print(f"📥 Bắt được 1 log mới, đang đẩy vào Logic Engine...") 
    try:
        # Giữ timeout thấp để vòng lặp không bị treo
        requests.post(LOGIC_ENGINE_URL, json={"raw_data": raw_log}, timeout=2)
    except Exception as e:
        print(f"❌ Lỗi gửi sang Logic Engine: {e}")