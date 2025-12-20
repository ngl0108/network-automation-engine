from fastapi import APIRouter
from app.api.v1.endpoints import devices, config, logs, config_template  # config_template 추가!

api_router = APIRouter()

api_router.include_router(devices.router, prefix="/devices", tags=["Devices"])
api_router.include_router(config.router, prefix="/config", tags=["Configuration"])
api_router.include_router(logs.router, prefix="/logs", tags=["Logs"])
api_router.include_router(config_template.router, prefix="/config-templates", tags=["Config Templates"])  # 추가!