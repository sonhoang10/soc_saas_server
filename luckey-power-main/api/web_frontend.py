import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="SOC Dashboard Frontend")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Route giao diện Login
@app.get("/login", response_class=HTMLResponse)
def serve_login():
    template_path = os.path.join(BASE_DIR, "templates", "login.html")
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h2>Không tìm thấy file templates/login.html</h2>"

# Route giao diện Dashboard (Trang chủ)
@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    template_path = os.path.join(BASE_DIR, "templates", "index.html")
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h2>Không tìm thấy file templates/index.html</h2>"