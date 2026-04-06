# 🛡️ Mèn Mén SOC SaaS - Hệ Thống Giám Sát & Phản Ứng Tự Động (Cloud-based SOC)

![Version](https://img.shields.io/badge/version-1.0.0--beta-blue.svg)
![Python](https://img.shields.io/badge/python-3.12-blue.svg)
![Node.js](https://img.shields.io/badge/node.js-v18+-green.svg)
![Kafka](https://img.shields.io/badge/kafka-3.7.0-red.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

**Mèn Mén SOC SaaS** là một giải pháp Trung tâm điều hành an ninh mạng (Security Operations Center) chạy trên nền tảng đám mây, được thiết kế tối ưu cho các doanh nghiệp vừa và nhỏ (SMEs). 

Dự án hướng tới việc đơn giản hóa bảo mật bằng cách thu thập log tập trung, phân tích dữ liệu theo thời gian thực để phát hiện các mối đe dọa (Brute-force, SQL Injection), và **tự động phản ứng (Active Defense)** để bảo vệ máy chủ của khách hàng mà không cần đội ngũ chuyên gia túc trực 24/7.

---

## ✨ Tính Năng Nổi Bật (Features)

* **📡 Thu Thập Log Tập Trung:** Tự động thu thập log từ Web App (Node.js) và hệ điều hành (SSH Auth) thông qua Filebeat.
* **⚡ Xử Lý Thời Gian Thực:** Sử dụng Kafka làm bộ đệm để xử lý khối lượng log lớn mà không gây nghẽn hệ thống.
* **🧠 Logic Engine Thông Minh:** Nhận diện tấn công Brute-force (Web/SSH) và SQL Injection ngay khi chúng xảy ra.
* **🛡️ Active Defense (Phản Ứng Tự Động):** Gửi lệnh trực tiếp đến server nạn nhân để chặn (Ban) IP của kẻ tấn công thông qua `iptables`.
* **📊 Live Dashboard:** Giao diện trực quan cập nhật cảnh báo liên tục qua WebSocket.

---

## 🏗️ Kiến Trúc Hệ Thống (Architecture)

Luồng xử lý dữ liệu (Data Flow) của hệ thống được chia thành 3 phần chính:

1.  **Client Target (Máy khách hàng):** Chạy ứng dụng web, sinh log. Cài đặt `Filebeat` để đẩy log đi và chạy `Agent (FastAPI)` để nhận lệnh chặn IP.
2.  **Trạm Trung Chuyển (Kafka Broker):** Đóng vai trò hứng toàn bộ log từ các máy khách hàng đưa vào topic `soc-raw-logs`.
3.  **SOC Server (Hệ thống trung tâm):** * *Consumer & Engine:* Hút log từ Kafka, phân tích bằng các tập luật (Rules/Regex).
    * *Backend:* Quản lý API và WebSocket đẩy dữ liệu lên Dashboard.
    * *Frontend:* Hiển thị giao diện người dùng.

---

## 📂 Cấu Trúc Thư Mục (Folder Structure)

```text
men-men-soc-saas/
├── client-target/          # Code cài đặt trên máy chủ của khách hàng
│   ├── web-test/           # Demo Web App (Node.js) sinh log
│   ├── active-defense/     # Agent nhận lệnh chặn IP (Python FastAPI)
│   └── filebeat.yml        # File cấu hình mẫu cho Filebeat
├── kafka-broker/           # Script tự động cài đặt Kafka KRaft
│   └── setup-kafka.sh      
├── soc-server/             # Mã nguồn Trung tâm SOC
│   ├── 1_kafka_consumer.py # Hút log từ Kafka
│   ├── 2_logic_engine.py   # Phân tích và phát hiện tấn công
│   ├── 3_web_backend.py    # API & WebSocket Server
│   └── index.html          # Dashboard giao diện
└── README.md               # Tài liệu dự án
```

---

## ⚙️ Yêu Cầu Môi Trường (Prerequisites)

Để vận hành hệ thống, máy của bạn cần có sẵn:
* **OS:** Ubuntu 20.04 / 22.04 (Khuyến nghị dùng Linux để test `iptables`)
* **Python:** 3.10 trở lên
* **Node.js:** v18+ & npm
* **Java:** OpenJDK 17 (Yêu cầu bắt buộc để chạy Kafka)

---

## 🚀 Hướng Dẫn Triển Khai (Deployment)
cai_dat.md

---

## 🧪 Hướng Dẫn Kiểm Thử (Testing)
Sau khi 4 thành phần trên đã chạy, bạn mở trình duyệt và truy cập: http://localhost:8000 (Hoặc IP Public của Server SOC) để mở Dashboard.
### Kịch bản 1: Test Brute-force Web
1. Truy cập Web Demo: http://localhost:3000
2. Cố tình đăng nhập sai 5-6 lần liên tục trong vòng 1 phút.
3. Quan sát Dashboard: Hệ thống sẽ báo động đỏ và gửi lệnh xuống Agent (Terminal 3) để iptables khóa IP của bạn lại.
### Kịch bản 2: Test SQL Injection
1. Tại form đăng nhập Web Demo, nhập tài khoản: admin' OR 1=1 --
2. Logic Engine sẽ lập tức bắt được chuỗi Regex nguy hiểm, cảnh báo SQLi sẽ xuất hiện trên Dashboard và IP của bạn bị ban ngay lập tức.

---

## 👥 Đội Ngũ Phát Triển (Mèn Mén VN)
* Đặng Xuân Thủy: Engine Developer (Thiết kế logic & rule cảnh báo)
* Nguyễn Minh Thái: Security Analyst (Phân tích bảo mật & Threat Intelligence)
* Nguyễn Tuấn Kiệt: Frontend Developer (Thiết kế giao diện UI/UX)
* Thái Hoàng Sơn: Backend Developer (Xây dựng kiến trúc hệ thống & API)
* Nguyễn Phú Trọng: Presenter & QA (Kiểm soát chất lượng, Quản lý tiến độ)

---
## 📜 Giấy Phép (License)
Dự án này được phát triển cho mục đích học tập và nghiên cứu, được phân phối dưới giấy phép MIT License. Bạn có thể tự do sao chép, chỉnh sửa và sử dụng hệ thống này.