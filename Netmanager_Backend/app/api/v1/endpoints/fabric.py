from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from pydantic import BaseModel

from app.db.session import get_db
from app.api import deps
from app.models.user import User
from app.services.fabric_service import FabricService

router = APIRouter()

class FabricGenerateRequest(BaseModel):
    spine_ids: List[int]
    leaf_ids: List[int]
    asn: int = 65000
    vni_base: int = 10000

@router.post("/generate")
def generate_fabric_config(
    request: FabricGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_network_admin)
):
    """
    Generate BGP EVPN (VXLAN) Configuration for Spine-Leaf Fabric.
    """
    service = FabricService(db)
    configs = service.generate_fabric_config(
        spines=request.spine_ids,
        leafs=request.leaf_ids,
        asn_base=request.asn,
        vni_base=request.vni_base
    )
    return configs
