#!/bin/bash
echo "=========================================================="
echo " 🏭 BẮT ĐẦU DỰNG TRẠM TRUNG CHUYỂN LOG (KAFKA KRAFT) 🏭 "
echo "=========================================================="

# Lấy IP Public của server hiện tại
PUBLIC_IP=$(curl -s ifconfig.me)
echo "👉 Phát hiện IP Public của Server Kafka là: $PUBLIC_IP"
read -p "Nhấn Enter để tiếp tục (hoặc nhập IP khác nếu IP trên sai): " USER_IP
if [ ! -z "$USER_IP" ]; then PUBLIC_IP=$USER_IP; fi

echo -e "\n⏳ [1/5] Đang cài đặt Java (Môi trường bắt buộc cho Kafka)..."
apt-get update -qq > /dev/null 2>&1
apt-get install openjdk-17-jre-headless -y -qq > /dev/null 2>&1

echo "⏳ [2/5] Đang tải Apache Kafka (v3.7.0)..."
wget -4 --show-progress https://archive.apache.org/dist/kafka/3.7.0/kafka_2.13-3.7.0.tgz
tar -xzf kafka_2.13-3.7.0.tgz
mv kafka_2.13-3.7.0 /opt/kafka
rm kafka_2.13-3.7.0.tgz

echo "⏳ [3/5] Đang cấu hình hệ thống mạng (Mở cổng đón Log từ xa)..."
# Sửa file cấu hình để Kafka cho phép các server khác (Filebeat) kết nối vào
sed -i "s/listeners=PLAINTEXT:\/\/localhost:9092,CONTROLLER:\/\/localhost:9093/listeners=PLAINTEXT:\/\/0.0.0.0:9092,CONTROLLER:\/\/localhost:9093/" /opt/kafka/config/kraft/server.properties
sed -i "s/#advertised.listeners=PLAINTEXT:\/\/localhost:9092/advertised.listeners=PLAINTEXT:\/\/$PUBLIC_IP:9092/" /opt/kafka/config/kraft/server.properties

echo "⏳ [4/5] Đang khởi tạo Cluster lưu trữ (KRaft mode)..."
KAFKA_CLUSTER_ID=$(/opt/kafka/bin/kafka-storage.sh random-uuid)
/opt/kafka/bin/kafka-storage.sh format -t $KAFKA_CLUSTER_ID -c /opt/kafka/config/kraft/server.properties > /dev/null

echo "⏳ [5/5] Đang thiết lập Kafka chạy ngầm dưới dạng Service..."
cat << 'SVC' > /etc/systemd/system/kafka.service
[Unit]
Description=Apache Kafka Server
Documentation=http://kafka.apache.org/documentation.html
Requires=network.target remote-fs.target
After=network.target remote-fs.target

[Service]
Type=simple
User=root
ExecStart=/opt/kafka/bin/kafka-server-start.sh /opt/kafka/config/kraft/server.properties
ExecStop=/opt/kafka/bin/kafka-server-stop.sh
Restart=on-abnormal

[Install]
WantedBy=multi-user.target
SVC

systemctl daemon-reload
systemctl enable kafka > /dev/null 2>&1
systemctl start kafka

# Đợi Kafka khởi động xong
sleep 5

echo "🎯 Đang tạo Topic 'soc-raw-logs' để hứng dữ liệu từ Web Client..."
/opt/kafka/bin/kafka-topics.sh --create --topic soc-raw-logs --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1 > /dev/null 2>&1

echo -e "\n=========================================================="
echo " ✅ CÀI ĐẶT KAFKA HOÀN TẤT VÀ ĐANG CHẠY! "
echo " 📡 Cổng giao tiếp: 9092"
echo " 📁 Topic đã tạo: soc-raw-logs"
echo " 🛑 (Quan trọng): Hãy đảm bảo Firewall trên DigitalOcean đã mở port 9092!"
echo "=========================================================="