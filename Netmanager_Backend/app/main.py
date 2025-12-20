from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from app.api.v1.router import api_router
from app.db.session import engine
from app.db.base import Base  # Base 임포트 (declarative_base)
from app.models import device  # device 모델
from app.models.log import EventLog  # EventLog 모델
from app.api.v1.endpoints.config_template import router as config_template_router  # 직접 임포트 추가
from contextlib import asynccontextmanager
from app.services.syslog_service import start_syslog_server
import threading

# 모든 모델 테이블 생성 (Base 사용)
Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting Scheduler...")

    print("🚀 Starting Syslog Server...")
    syslog_thread = threading.Thread(target=start_syslog_server, daemon=True)
    syslog_thread.start()

    yield

    print("🛑 Stopping Scheduler and Syslog Server...")

app = FastAPI(
    title="NetManager API",
    description="Network Management System Backend API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 기존 라우터 등록
app.include_router(api_router, prefix="/api/v1")

# config_template 라우터 직접 등록 (임시 해결)
from app.api.v1.endpoints.config_template import router as config_template_router
app.include_router(config_template_router, prefix="/api/v1/config-templates", tags=["Config Templates"])
@app.get("/")
def read_root():
    return {"message": "Welcome to NetManager API Server! System is Online."}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)