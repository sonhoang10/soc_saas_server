import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
import clickhouse_connect
from dotenv import load_dotenv

# TÍCH HỢP POSTGRESQL TỪ MODULE DATABASE
from api.database import test_db_connection

#auth lib
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from api.database import get_db
from api.models import User
from api.auth_utils import get_password_hash, verify_password, create_access_token
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# 1. CẤU HÌNH LOGGING DOANH NGHIỆP
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [WEB_BACKEND] - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Biến toàn cục chứa DB Client
ch_client = None

# 2. QUẢN LÝ VÒNG ĐỜI (LIFESPAN)
@asynccontextmanager
async def lifespan(app: FastAPI):
    global ch_client
    
    # 2.1 Khởi tạo ClickHouse 
    try:
        logger.info("Đang kết nối tới ClickHouse...")
        ch_client = clickhouse_connect.get_client(
            host=os.getenv("CH_HOST", "localhost"),
            port=int(os.getenv("CH_PORT", 8123)),
            username=os.getenv("CH_USER", "default"),
            password=os.getenv("CH_PASS", "")
        )
        logger.info("✅ Kết nối ClickHouse thành công!")
    except Exception as e:
        logger.error(f"❌ Lỗi khởi tạo ClickHouse: {e}")

    # 2.2 Kiểm tra PostgreSQL
    logger.info("Đang kết nối tới PostgreSQL...")
    is_pg_ok, pg_msg = test_db_connection()
    if is_pg_ok:
        logger.info(pg_msg)
    else:
        logger.error(pg_msg)
        
    yield
    
    # Đóng kết nối khi tắt Server
    logger.info("Đóng kết nối ClickHouse...")
    ch_client = None

app = FastAPI(title="SOC Web Backend", lifespan=lifespan)

# 3. BẢO MẬT CORS 
origins_str = os.getenv("ALLOWED_ORIGINS", "*")
allowed_origins = origins_str.split(",") if origins_str != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client kết nối WebSocket. Tổng: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Client ngắt WebSocket. Tổng: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Lỗi gửi tin nhắn WS: {e}")

manager = ConnectionManager()

class AlertPayload(BaseModel):
    time: str
    level: str
    type: str
    ip: str
    analysis: str
    target_ip: Optional[str] = "Unknown"
    target_server: Optional[str] = "Unknown"
    server: Optional[str] = "Unknown"

@app.post("/api/alerts")
async def receive_alert(alert: AlertPayload):
    logger.warning(f"Báo động đỏ: {alert.type} từ IP {alert.ip} tấn công {alert.target_server}")
    await manager.broadcast(alert.model_dump())
    return {"status": "Broadcasted"}

@app.websocket("/ws/alerts")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/api/logs")
def get_all_logs(limit: int = 50):
    if not ch_client:
        return {"error": "Database ClickHouse chưa sẵn sàng"}
    
    safe_limit = min(max(1, limit), 1000) 
    
    try:
        query = f"SELECT timestamp, target_ip, log_type, action, username FROM soc_db.raw_logs ORDER BY timestamp DESC LIMIT {safe_limit}"
        result = ch_client.query(query)
        
        logs = []
        for row in result.result_rows:
            logs.append({
                "timestamp": str(row[0]) if row[0] else "",
                "target_ip": str(row[1]) if row[1] else "-",
                "log_type": str(row[2]) if row[2] else "N/A",
                "action": str(row[3]) if row[3] else "Unknown",
                "username": str(row[4]) if row[4] else "-"
            })
            
        return {"logs": logs} 
    
    except Exception as e:
        logger.error(f"Lỗi truy vấn ClickHouse: {e}")
        return {"error": "Lỗi nội bộ máy chủ"}
    
# Schema cho Đăng ký
class UserCreate(BaseModel):
    email: str
    username: str
    password: str

# API Đăng ký
@app.post("/api/auth/register")
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    # 1. Kiểm tra email tồn tại chưa
    user_exists = db.query(User).filter(User.email == user_data.email).first()
    if user_exists:
        raise HTTPException(status_code=400, detail="Email này đã được đăng ký!")
    
    # 2. Băm mật khẩu và lưu
    new_user = User(
        email=user_data.email,
        username=user_data.username,
        password_hash=get_password_hash(user_data.password)
    )
    db.add(new_user)
    db.commit()
    return {"message": "Đăng ký thành công"}

# API Đăng nhập
@app.post("/api/auth/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # form_data.username ở đây chính là Email từ Frontend gửi lên
    user = db.query(User).filter(User.email == form_data.username).first()
    
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email hoặc mật khẩu không chính xác",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Tạo JWT Token
    access_token = create_access_token(data={"sub": user.email, "user_id": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}