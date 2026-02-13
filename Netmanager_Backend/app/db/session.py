import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# ========================================
# Database Configuration
# ========================================
# 1. 환경변수에서 DATABASE_URL을 읽음 (Production: PostgreSQL)
# 2. 환경변수가 없으면 SQLite 사용 (Local Development)
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "sqlite:///./netmanager.db"
)

# ========================================
# Engine Configuration
# ========================================
# SQLite는 check_same_thread 옵션 필요, PostgreSQL은 불필요
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL, 
        connect_args={"check_same_thread": False}
    )
else:
    # PostgreSQL / MySQL 등
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True  # Connection Health Check
    )

# 세션 생성기
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 모델들이 상속받을 기본 클래스
Base = declarative_base()

# DB 세션 의존성 주입 함수 (API에서 사용)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()