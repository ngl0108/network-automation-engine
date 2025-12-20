from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# SQLite 파일 경로 (나중에 PostgreSQL URL로만 바꾸면 바로 전환됨)
SQLALCHEMY_DATABASE_URL = "sqlite:///./netmanager.db"

# 커넥션 풀 생성 (check_same_thread는 SQLite 전용 옵션)
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
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