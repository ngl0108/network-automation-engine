from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import asyncio
from contextlib import asynccontextmanager
import logging

from app.core.logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

# [중요] Celery 앱 로드
try:
    import celery_app
except ImportError:
    logger.warning("Celery not found. Task scheduling will be disabled.")
    celery_app = None

from app.api.v1.router import api_router
from app.db.session import engine, Base
from app.models import device as device_models
from app.models import user as user_models
from app.models import automation # [NEW] Automation Rules
from app.models import ztp_queue as ztp_models  # [NEW] ZTP 모델 임포트
from app.models import discovery # [NEW] Discovery Models
from app.models import topology # [NEW] Topology Layout
from app.models import topology_candidate
from app.models import endpoint
from app.models import device_inventory
from app.models import visual_config
from app.models import approval # [NEW] Approval
from app.models import credentials
from app.services.syslog_service import SyslogProtocol  
from app.services.netflow_collector import NetflowProtocol
from app.services.snmp_trap_service import SnmpTrapServer
from app.core import security
from app.db.session import SessionLocal
from app.db.migrations import run_migrations
import secrets

# DB 테이블 자동 생성 (Base는 모든 모델에서 공유됨)
Base.metadata.create_all(bind=engine)
run_migrations(engine)



@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("NetManager API Server Starting...")
    scheduler = None

    # Create Default Admin User
    db = SessionLocal()
    try:
        admin = db.query(user_models.User).filter(user_models.User.username == "admin").first()
        if not admin:
            logger.info("Creating default admin user...")
            hashed_pw = security.get_password_hash("admin123")
            new_admin = user_models.User(
                username="admin",
                hashed_password=hashed_pw,
                full_name="System Administrator",
                role="admin",
                is_active=True
            )
            db.add(new_admin)
            db.commit()
            logger.info("Default admin created")

        system_user = db.query(user_models.User).filter(user_models.User.username == "system").first()
        if not system_user:
            hashed_pw = security.get_password_hash(secrets.token_urlsafe(32))
            new_system = user_models.User(
                username="system",
                hashed_password=hashed_pw,
                full_name="System Automation",
                role="admin",
                is_active=True,
            )
            db.add(new_system)
            db.commit()
        
        # [NEW] Seed default configuration templates
        from app.services.default_templates import seed_default_templates
        seed_default_templates(db)
        
    except Exception as e:
        logger.exception("Failed to create default admin")
    finally:
        db.close()

    # =========================================================
    # [핵심] FastAPI 시작 시 Syslog 서버(UDP 514) 백그라운드 실행
    # =========================================================
    loop = asyncio.get_running_loop()
    try:
        # 0.0.0.0:514 포트로 바인딩
        # 주의: 1024번 이하 포트는 관리자 권한(Root/Admin)이 필요할 수 있음
        # 권한 에러 시 포트를 5140으로 변경하세요.
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: SyslogProtocol(),
            local_addr=('0.0.0.0', 514)
        )
        logger.info("Syslog Server is running on UDP port 514 (Integrated)")
    except PermissionError:
        logger.warning("Port 514 requires Admin privileges. Syslog server failed to start.")
    except Exception as e:
        logger.exception("Syslog server failed to start")

    try:
        trap_server = SnmpTrapServer(host="0.0.0.0", port=162, community="public")
        trap_server.start()
        logger.info("SNMP Trap Receiver is running on UDP port 162 (v2c)")
    except PermissionError:
        try:
            trap_server = SnmpTrapServer(host="0.0.0.0", port=2162, community="public")
            trap_server.start()
            logger.info("SNMP Trap Receiver is running on UDP port 2162 (v2c)")
        except Exception as e:
            logger.exception("SNMP Trap receiver failed to start")
    except Exception as e:
        logger.exception("SNMP Trap receiver failed to start")

    try:
        transport_nf, protocol_nf = await loop.create_datagram_endpoint(
            lambda: NetflowProtocol(),
            local_addr=("0.0.0.0", 2055),
        )
        logger.info("NetFlow Collector is running on UDP port 2055 (v5)")
    except Exception as e:
        logger.exception("NetFlow collector failed to start")

    # =========================================================
    # [Optional] ZTP DHCP Server Start (UDP 67)
    # =========================================================
    try:
        from app.services.dhcp_service import start_dhcp_server_if_enabled
        # 기본적으로 활성화 (Lab 테스트 위함)
        start_dhcp_server_if_enabled()
    except Exception as e:
        logger.exception("DHCP Failed to initialize builtin DHCP")

    try:
        from app.services.auto_discovery_scheduler import AutoDiscoveryScheduler
        scheduler = AutoDiscoveryScheduler()
        scheduler.start()
        app.state.auto_discovery_scheduler = scheduler
        logger.info("Auto Discovery Scheduler started (settings-controlled)")
    except Exception as e:
        logger.exception("Auto Discovery Scheduler failed to start")

    yield

    try:
        sch = getattr(app.state, "auto_discovery_scheduler", None) or scheduler
        if sch:
            sch.stop()
    except Exception:
        pass

    logger.info("NetManager API Server Stopping...")


app = FastAPI(title="NetManager API", lifespan=lifespan)

try:
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    from app.observability.device_metrics import register_device_metrics

    register_device_metrics(cache_ttl_seconds=10)
except Exception:
    pass

# CORS 설정 (프론트엔드 연동용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# [NEW] Response Wrapper (standardize success payload for JSON responses)
from app.middleware.response_wrapper import ResponseWrapperMiddleware
app.add_middleware(ResponseWrapperMiddleware)

# [NEW] Request Context (request_id/path/method propagation)
from app.middleware.request_context import RequestContextMiddleware
app.add_middleware(RequestContextMiddleware)

# [NEW] Audit Middleware Registration
from app.middleware.audit import AuditMiddleware
app.add_middleware(AuditMiddleware)

from fastapi import Request, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.api_response import fail

@app.exception_handler(HTTPException)
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: Exception):
    status_code = int(getattr(exc, "status_code", 500) or 500)
    detail = getattr(exc, "detail", None)
    details = None
    message = "HTTP error"
    if isinstance(detail, str):
        message = detail
    elif isinstance(detail, dict):
        details = detail
        message = str(detail.get("message") or detail.get("detail") or message)
    elif detail is not None:
        details = detail
    return fail(
        status_code=status_code,
        code=f"HTTP_{status_code}",
        message=message,
        details=details,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return fail(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="VALIDATION_ERROR",
        message="Request validation failed",
        details=exc.errors(),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception", extra={"path": str(request.url.path), "method": request.method})
    return fail(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="INTERNAL_SERVER_ERROR",
        message="Internal Server Error",
    )

app.include_router(api_router, prefix="/api/v1")


@app.get("/")
def read_root():
    return {"message": "NetManager API Server is Running!"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True, log_config=None)
