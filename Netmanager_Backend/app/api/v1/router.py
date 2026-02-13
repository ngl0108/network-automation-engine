from fastapi import APIRouter
from app.api.v1.endpoints import (
    devices, sites, logs, misc, auth, # [FIX] auth 추가
    config, config_template, variables, compliance,
    jobs,
    images, policy, settings, ztp, audit, topology, fabric, discovery, visual_config, approval, traffic, snmp_profiles, observability, automation_hub # [NEW] Approval
)

api_router = APIRouter()

# 기존 라우터
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(devices.router, prefix="/devices", tags=["devices"])
api_router.include_router(sites.router, prefix="/sites", tags=["sites"])
api_router.include_router(logs.router, prefix="/logs", tags=["logs"])
api_router.include_router(misc.router, prefix="/sdn", tags=["sdn"])

# [NEW] 자동화 라우터
api_router.include_router(config.router, prefix="/config", tags=["config"])
api_router.include_router(config_template.router, prefix="/templates", tags=["templates"])
api_router.include_router(variables.router, prefix="/vars", tags=["variables"])
api_router.include_router(compliance.router, prefix="/compliance", tags=["compliance"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(approval.router, prefix="/approval", tags=["approval"])

# [NEW] 확장 기능 라우터 (프론트엔드 경로 맞춤)
api_router.include_router(images.router, prefix="/sdn/images", tags=["images"])
api_router.include_router(policy.router, prefix="/sdn/policies", tags=["policies"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])

# [NEW] ZTP (Zero Touch Provisioning)
# [NEW] ZTP (Zero Touch Provisioning)
api_router.include_router(ztp.router, prefix="/ztp", tags=["ztp"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])

# [NEW] Topology & Path Trace
api_router.include_router(topology.router, prefix="/topology", tags=["topology"])
api_router.include_router(fabric.router, prefix="/fabric", tags=["fabric"])
api_router.include_router(discovery.router, prefix="/discovery", tags=["discovery"])
api_router.include_router(visual_config.router, prefix="/visual", tags=["visual"])
api_router.include_router(traffic.router, prefix="/traffic", tags=["traffic"])
api_router.include_router(snmp_profiles.router, prefix="/snmp-profiles", tags=["snmp-profiles"])
api_router.include_router(observability.router, prefix="/observability", tags=["observability"])
api_router.include_router(automation_hub.router, prefix="/automation-hub", tags=["automation-hub"])

