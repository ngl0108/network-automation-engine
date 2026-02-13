from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Literal, Dict, Any
from pydantic import BaseModel
from app.db.session import get_db
from app.models.device import Site, Device

router = APIRouter()

class VariableUpdate(BaseModel):
    variables: Dict[str, Any]

@router.put("/{target_type}/{target_id}")
def update_variables(
    target_type: Literal["site", "device"],
    target_id: int,
    var_in: VariableUpdate,
    db: Session = Depends(get_db)
):
    if target_type == "site":
        item = db.query(Site).filter(Site.id == target_id).first()
    else:
        item = db.query(Device).filter(Device.id == target_id).first()

    if not item:
        raise HTTPException(404, detail="Target not found")

    item.variables = var_in.variables
    # SQLAlchemy JSON 변경 감지 강제
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(item, "variables")

    db.commit()
    return {"status": "success", "variables": item.variables}