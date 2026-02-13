from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from pydantic import BaseModel
from app.db.session import get_db
from app.models.device import ConfigTemplate, Device
from app.api import deps
from app.models.user import User
from app.services.template_service import TemplateRenderer
from app.services.template_service import TemplateRenderer
from app.services.ssh_service import DeviceConnection, DeviceInfo
from concurrent.futures import ThreadPoolExecutor, as_completed

router = APIRouter()
# Reload Trigger

def _deploy_worker(target: Dict[str, Any], template_content: str):
    """
    Worker function for parallel deployment.
    target dict contains: dev_id, device_info_args, context
    """
    dev_id = target['dev_id']
    try:
        # 1. Render Template
        config_text = TemplateRenderer.render(template_content, target['context'])

        # 2. Connection Info
        info = DeviceInfo(**target['device_info_args'])
        
        # 3. Connect & Push
        conn = DeviceConnection(info)
        if conn.connect():
            # Use the send_config_set wrapper we added
            output = conn.send_config_set(config_text.splitlines())
            conn.disconnect()
            return {"id": dev_id, "status": "success", "output": output}
        else:
            return {"id": dev_id, "status": "failed", "error": f"Connection Failed: {conn.last_error}"}

    except Exception as e:
        return {"id": dev_id, "status": "failed", "error": str(e)}


# --- Schemas ---
class ConfigTemplateCreate(BaseModel):
    name: str
    category: str = "Switching"
    content: str
    tags: str = "v1.0"


class ConfigTemplateResponse(ConfigTemplateCreate):
    id: int

    class Config: from_attributes = True


class TemplatePreviewRequest(BaseModel):
    device_id: int
    template_content: str


class TemplateDeployRequest(BaseModel):
    device_ids: List[int]
    variables: Dict[str, Any] = {}


# --- Endpoints ---

@router.get("/", response_model=List[ConfigTemplateResponse])
def get_templates(db: Session = Depends(get_db), current_user: User = Depends(deps.require_viewer)):
    return db.query(ConfigTemplate).all()


@router.post("/", response_model=ConfigTemplateResponse)
def create_template(template: ConfigTemplateCreate, db: Session = Depends(get_db), current_user: User = Depends(deps.require_network_admin)):
    db_obj = ConfigTemplate(**template.dict())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@router.put("/{template_id}", response_model=ConfigTemplateResponse)
def update_template(template_id: int, template_in: ConfigTemplateCreate, db: Session = Depends(get_db), current_user: User = Depends(deps.require_network_admin)):
    db_obj = db.query(ConfigTemplate).filter(ConfigTemplate.id == template_id).first()
    if not db_obj:
        raise HTTPException(status_code=404, detail="Template not found")
    
    for key, value in template_in.dict().items():
        setattr(db_obj, key, value)
    
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@router.delete("/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db), current_user: User = Depends(deps.require_network_admin)):
    db_obj = db.query(ConfigTemplate).filter(ConfigTemplate.id == template_id).first()
    if not db_obj:
        raise HTTPException(status_code=404, detail="Template not found")
    
    db.delete(db_obj)
    db.commit()
    return {"message": "Template deleted successfully"}


@router.post("/validate")
def validate_template(req: TemplatePreviewRequest, db: Session = Depends(get_db), current_user: User = Depends(deps.require_network_admin)):
    """
    Check for missing variables without rendering
    """
    device = db.query(Device).filter(Device.id == req.device_id).first()
    if not device: raise HTTPException(404, "Device not found")

    context = device.variables or {}
    context.update({"device": {"name": device.name, "ip": device.ip_address}})
    
    missing = TemplateRenderer.validate_context(req.template_content, context)
    return {
        "valid": len(missing) == 0,
        "missing_variables": missing
    }

@router.post("/preview")
def preview_template(req: TemplatePreviewRequest, db: Session = Depends(get_db), current_user: User = Depends(deps.require_viewer)):
    device = db.query(Device).filter(Device.id == req.device_id).first()
    if not device: raise HTTPException(404, "Device not found")

    context = device.variables or {}
    context.update({"device": {"name": device.name, "ip": device.ip_address}})

    # Validation Check
    missing = TemplateRenderer.validate_context(req.template_content, context)
    if missing:
        raise HTTPException(400, f"Missing variables: {', '.join(missing)}")

    rendered = TemplateRenderer.render(req.template_content, context)
    return {"rendered_config": rendered}


@router.post("/{template_id}/deploy")
def deploy_template(template_id: int, req: TemplateDeployRequest, db: Session = Depends(get_db), current_user: User = Depends(deps.require_network_admin)):
    template = db.query(ConfigTemplate).filter(ConfigTemplate.id == template_id).first()
    if not template: raise HTTPException(404, "Template not found")

    # 1. Prepare Target List (Main Thread)
    targets = []
    for dev_id in req.device_ids:
        dev = db.query(Device).filter(Device.id == dev_id).first()
        if not dev: continue

        # Context Preparation
        context = dev.variables or {}
        context.update({"device": {"name": dev.name, "ip": dev.ip_address}, "_dev_id": dev.id})
        context.update(req.variables)

        # Device Info
        dev_args = {
            "host": dev.ip_address,
            "username": dev.ssh_username,
            "password": dev.ssh_password,
            "secret": dev.enable_password,
            "port": dev.ssh_port or 22,
            "device_type": dev.device_type or 'cisco_ios'
        }

        targets.append({
            "dev_id": dev.id,
            "context": context,
            "device_info_args": dev_args
        })

    # 2. Execute in Parallel
    results = []
    # Adjust max_workers as needed (e.g., 20)
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_map = {
            executor.submit(_deploy_worker, target, template.content): target['dev_id']
            for target in targets
        }

        for future in as_completed(future_map):
            try:
                res = future.result()
                results.append(res)
            except Exception as e:
                dev_id = future_map[future]
                results.append({"id": dev_id, "status": "failed", "error": str(e)})

    return {"summary": results}