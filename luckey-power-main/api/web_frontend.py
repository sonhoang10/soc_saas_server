import secrets
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse

app = FastAPI()
security = HTTPBasic()

# 🔴 THAY ĐỔI TÀI KHOẢN / MẬT KHẨU TẠI ĐÂY 🔴
USERNAME = "menmen"
PASSWORD = "3667"

def verify_login(credentials: HTTPBasicCredentials = Depends(security)):
    is_user_ok = secrets.compare_digest(credentials.username, USERNAME)
    is_pass_ok = secrets.compare_digest(credentials.password, PASSWORD)
    if not (is_user_ok and is_pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sai tài khoản hoặc mật khẩu!",
            headers={"WWW-Authenticate": "Basic"}, # Kích hoạt hộp thoại đăng nhập của trình duyệt
        )
    return credentials.username

@app.get("/", response_class=HTMLResponse)
def serve_dashboard(username: str = Depends(verify_login)):
    # Chỉ khi đăng nhập đúng mới đọc và hiển thị file index.html
    try:
        with open("../templates/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>Lỗi: Không tìm thấy file index.html</h1>"