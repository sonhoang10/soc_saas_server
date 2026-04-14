import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

DATABASE_URL = os.getenv("DATABASE_URL")

# 1. KHỞI TẠO ENGINE KẾT NỐI
# pool_pre_ping=True: Tự động kiểm tra kết nối bị đứt để kết nối lại (Chuẩn Production)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# 2. KHỞI TẠO SESSION & BASE MODEL
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 3. HÀM KIỂM TRA KẾT NỐI
def test_db_connection():
    """Hàm này dùng để kiểm tra cấu hình PostgreSQL khi Backend khởi động"""
    try:
        with engine.connect() as conn:
            return True, "✅ Kết nối PostgreSQL thành công!"
    except Exception as e:
        return False, f"❌ Lỗi kết nối PostgreSQL: {e}"

# 4. DEPENDENCY DÙNG CHO FASTAPI
def get_db():
    """Cấp phát session độc lập cho mỗi request và tự động đóng khi xong"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()