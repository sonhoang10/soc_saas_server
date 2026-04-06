#!/bin/bash
# Di chuyển đúng vào thư mục chứa code
cd /root/web-test-soc
# Kích hoạt môi trường ảo
source soc_env/bin/activate
# Chạy uvicorn (dùng exec để PM2 quản lý trực tiếp tiến trình này)
exec uvicorn agent:app --host 0.0.0.0 --port 8001