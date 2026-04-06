#!/bin/bash
echo "=========================================================="
echo " 🚀 BẮT ĐẦU CÀI ĐẶT MÈN MÉN SOC AGENT (FILEBEAT) 🚀 "
echo "=========================================================="

read -p "👉 Nhập địa chỉ IP của Server Kafka (VD: 10.11.12.13): " KAFKA_IP

if [ -z "$KAFKA_IP" ]; then
    echo "❌ Lỗi: Bạn chưa nhập IP. Hủy cài đặt!"
    exit 1
fi

echo -e "\n⏳ [1/4] Đang thiết lập môi trường..."
wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | sudo gpg --dearmor -o /usr/share/keyrings/elastic-keyring.gpg --yes > /dev/null 2>&1
sudo apt-get install apt-transport-https -y -qq > /dev/null 2>&1
echo "deb [signed-by=/usr/share/keyrings/elastic-keyring.gpg] https://artifacts.elastic.co/packages/8.x/apt stable main" | sudo tee /etc/apt/sources.list.d/elastic-8.x.list > /dev/null

echo "⏳ [2/4] Đang tải Filebeat..."
sudo apt-get update -qq > /dev/null 2>&1
sudo apt-get install filebeat -y -qq > /dev/null 2>&1

echo "⏳ [3/4] Đang cấu hình Agent kết nối về Kafka ($KAFKA_IP:9092)..."
sudo mv /etc/filebeat/filebeat.yml /etc/filebeat/filebeat.yml.bak 2>/dev/null

cat << CONFIG | sudo tee /etc/filebeat/filebeat.yml > /dev/null
filebeat.inputs:
- type: filestream
  id: os-auth-logs
  enabled: true
  paths:
    - /var/log/auth.log
  fields:
    log_type: "os_ssh_auth"

- type: filestream
  id: web-pm2-logs
  enabled: true
  paths:
    - /root/.pm2/logs/web-login-out.log
  fields:
    log_type: "web_app_login"
  parsers:
    - ndjson:
        target: "app_data"
        add_error_key: true

processors:
  - add_host_metadata:
      netinfo.enabled: true

output.kafka:
  enabled: true
  hosts: ["$KAFKA_IP:9092"]
  topic: "soc-raw-logs"
  partition.round_robin:
    reachable_only: false
  required_acks: 1
  compression: gzip
  max_message_bytes: 1000000
CONFIG

echo "⏳ [4/4] Đang khởi động dịch vụ..."
sudo systemctl daemon-reload
sudo systemctl enable filebeat > /dev/null 2>&1
sudo systemctl restart filebeat

echo -e "\n=========================================================="
echo " ✅ HOÀN TẤT! AGENT ĐANG GỬI LOG VỀ KAFKA: $KAFKA_IP"
echo "=========================================================="