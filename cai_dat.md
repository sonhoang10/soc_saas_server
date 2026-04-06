# 🛡️HƯỚNG DẪN CÀI ĐẶT HỆ THỐNG MÈN MÉN SOC SAAS
Tài liệu này hướng dẫn cài đặt từ đầu trên 3 Server trống. Hãy đảm bảo bạn đã mở các Port sau trên Firewall của Digital Ocean:
* Kafka Server: 9092
* Client Server: 80 (Web), 8001 (Agent)
* Main Server: 8000 (Backend), 8001 (Logic), 8080 (Frontend)

---

## 🏗️CÀI ĐẶT KAFKA SERVER (TRẠM TRUNG CHUYỂN)
1. Chạy script cài đặt tự động: Bạn có thể sử dụng nội dung file cai-kafka.sh.
```bash
# Tải và chạy script của bạn
chmod +x kafka/cai-kafka.sh
sudo ./kafka/cai-kafka.sh
```
2. Kiểm tra: Đảm bảo service Kafka đã chạy:
```bash
sudo systemctl status kafka
```
Lưu ý: Ghi lại Public IP của server này để điền vào Client và Main Server.

---

## 🖥️ 2. CÀI ĐẶT CLIENT SERVER (NẾU BẠN MUỐN TEST)
1. Cài đặt Web App (Test):
```bash
sudo apt update && sudo apt install nodejs npm -y
sudo npm install pm2 -g
cd ~/client/web-test-soc
npm install express body-parser
pm2 start server.js --name "web-login"
```
2. Cài đặt Filebeat & Agent:
```bash
# Cài đặt môi trường Python cho Agent
python3 -m venv soc_env
source soc_env/bin/activate
pip install fastapi uvicorn pydantic

# Chạy script cài đặt Filebeat (Nhập IP Kafka khi được hỏi)
chmod +x cai-dat-soc.sh
sudo ./cai-dat-soc.sh

# Chạy Agent phản ứng (Active Response) bằng PM2
chmod +x start_agent.sh
pm2 start ./start_agent.sh --name "soc-agent"
```

---

## 🧠 3. CÀI ĐẶT MAIN SERVER (TRUNG TÂM XỬ LÝ)
1. Thiết lập môi trường Python:
```bash
sudo apt update && sudo apt install python3-pip python3.12-venv nodejs npm -y
sudo npm install pm2 -g
cd ~/luckey-power-main
python3 -m venv soc_env
source soc_env/bin/activate
pip install -r requirements.txt
```
2. Cấu hình biến môi trường (.env):
* Tạo file .env để quản lý tập trung các IP:
```bash
KAFKA_IP=IP_CUA_SERVER_KAFKA
MAIN_SERVER_IP=IP_CUA_MAIN_SERVER
CLIENT_IP=IP_CUA_CLIENT
```
3. Khởi chạy hệ thống bằng PM2 (Theo cấu trúc mới):
```bash
# 1. Web Backend (API Dashboard)
pm2 start "./soc_env/bin/uvicorn api.web_backend:app --host 0.0.0.0 --port 8000" --name "soc-backend"

# 2. Logic Engine (Phân tích log)
pm2 start "./soc_env/bin/uvicorn core.logic_engine:app --host 0.0.0.0 --port 8001" --name "soc-logic"

# 3. Kafka Consumer (Hút log từ Kafka)
pm2 start "./soc_env/bin/python core/kafka_consumer.py" --name "soc-consumer"

# 4. Web Frontend (Giao diện bảo mật)
pm2 start "./soc_env/bin/uvicorn api.web_frontend:app --host 0.0.0.0 --port 8080" --name "soc-frontend"

pm2 save
pm2 startup
```

---

## 🔍 4. KIỂM TRA LUỒNG DỮ LIỆU (DATA FLOW)
1. Check Log Kafka: Xem log có đổ về từ Client không?
```bash
/opt/kafka/bin/kafka-console-consumer.sh --topic soc-raw-logs --bootstrap-server localhost:9092
```
2. Check Log Consumer: Xem Main Server có hút được log không?
```bash
pm2 logs soc-consumer
```
3. Check Logic Engine: Xem có phát hiện tấn công (SQLi/Brute-force) không?
```bash
pm2 logs soc-logic
```
4. Truy cập Dashboard: Mở trình duyệt vào http://<IP_MAIN_SERVER>:8080 (Tài khoản: menmen / Pass: 3667).


---

## 🛠️ CÁC LỆNH CỨU HỘ NHANH
* Mở khóa toàn bộ IP trên Client (Nếu lỡ tay ban nhầm chính mình):
```bash
iptables -S INPUT | grep ' -j DROP' | sed 's/-A /-D /' | while read rule; do iptables $rule; done
```
* Xem bảng điều khiển PM2:
```bash
pm2 list
pm2 monit
```