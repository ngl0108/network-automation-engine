from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from typing import Dict, Any, Optional
from pydantic import BaseModel
import os
import logging
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.ztp_queue import ZtpQueue, ZtpStatus
from app.models.device import Device, Link
from app.schemas.ztp import ZtpRegisterRequest, ZtpApproveRequest
from datetime import datetime
from app.services.audit_service import AuditService
from app.api import deps
from app.models.user import User

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/boot", response_class=PlainTextResponse)
def get_boot_script(request: Request):
    """
    Serves the Python bootstrap script (ztp_boot.py).
    Dynamically injects the Server IP/Port based on the request host.
    """
    # Host header includes port (e.g., 192.168.1.100:8000)
    host_header = request.headers.get("host", "127.0.0.1:8000")
    if ":" in host_header:
        server_ip, server_port = host_header.split(":")
    else:
        server_ip, server_port = host_header, "80"

    file_path = os.path.join("app", "templates", "ztp_boot.py")
    
    if not os.path.exists(file_path):
        return "# [Error] ztp_boot.py template not found on server."

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Inject Server Info
    content = content.replace("{{ server_ip }}", server_ip)
    content = content.replace("{{ server_port }}", server_port)
    
    return content

@router.post("/register")
def register_device(payload: ZtpRegisterRequest, db: Session = Depends(get_db)):
    """
    Receives registration request.
    Creates/Updates ZtpQueue entry.
    Matches topology for RMA suggestion.
    """
    uplink = payload.uplink_info or {}
    logger.info(
        "ZTP register request serial=%s uplink_name=%s uplink_port=%s",
        payload.serial_number,
        uplink.get("name"),
        uplink.get("port"),
    )

    # 1. ZTP Queue Entry
    queue_item = db.query(ZtpQueue).filter(ZtpQueue.serial_number == payload.serial_number).first()
    if not queue_item:
        queue_item = ZtpQueue(
            serial_number=payload.serial_number,
            status=ZtpStatus.NEW.value,
            platform=payload.model
        )
        db.add(queue_item)
    
    # Update Basic Info
    queue_item.ip_address = payload.ip_address
    queue_item.platform = payload.model
    
    # 2. RMA / Topology Matching
    uplink = payload.uplink_info
    if uplink and uplink.get('name') and uplink.get('port'):
        u_name = uplink['name']
        u_port = uplink['port']
        
        queue_item.detected_uplink_name = u_name
        queue_item.detected_uplink_port = u_port
        queue_item.detected_uplink_ip = uplink.get('ip')

        # Find Link (Topology Match)
        # Search for a Link where Target == UplinkDevice AND TargetPort == UplinkPort
        # Note: Name matching might need normalization (Gi1/0/1 vs GigabitEthernet1/0/1)
        # For now, using naive like matching or exact match
        
        # Uplink Device
        uplink_dev = db.query(Device).filter(Device.name.ilike(f"%{u_name}%")).first()
        
        if uplink_dev:
            # Find the link connected to this uplink port
            # We are looking for the 'Source' device (the one that was here before)
            # Link Direction: Source(Downlink) -> Target(Uplink)
            
            # Case 1: Link is Source->Target (Downlink->Uplink)
            link = db.query(Link).filter(
                Link.target_device_id == uplink_dev.id,
                Link.target_interface_name.ilike(f"%{u_port}%")
            ).first()
            
            candidate_dev = link.source_device if link else None
            
            if candidate_dev:
                logger.info("ZTP RMA candidate found device=%s status=%s", candidate_dev.name, candidate_dev.status)
                
                # Check if authorized for auto-replacement
                if candidate_dev.status == 'replace_pending':
                    # TODO: Auto Assign Logic (Assign Backup Config or Template)
                    queue_item.suggested_reason = "Auto-Matched (Replace Pending)"
                    queue_item.suggested_device_id = candidate_dev.id
                    # For safety, we still might want 'wait' unless completely trusted
                    # But here, let's mark it as suggested
                else:
                    queue_item.suggested_device_id = candidate_dev.id
                    queue_item.suggested_reason = f"Topology Match: Connected to {u_name} on {u_port}"
            else:
                queue_item.suggestion_reason = f"Uplink found ({u_name}), but no previous device mapped to port {u_port}"
        else:
             queue_item.suggestion_reason = f"Uplink device '{u_name}' not found in inventory"

    db.commit()
    db.refresh(queue_item)

    # 3. Determine Response Action
    if queue_item.status == ZtpStatus.PROVISIONING.value and queue_item.assigned_template:
        # Render Config
        return {
            "action": "configure",
            "config_content": "hostname " + (queue_item.target_hostname or "NewDevice")  # Simple Mock
        }
    
    return {
        "action": "wait", 
        "status": queue_item.status,
        "message": "Registered in Queue. Waiting for approval."
    }

@router.post("/queue/{item_id}/approve")
def approve_device(item_id: int, payload: ZtpApproveRequest, db: Session = Depends(get_db), current_user: User = Depends(deps.require_network_admin)):
    """
    Approve a ZTP queue item. 
    Can either assign manual Site/Template OR Swap with an existing device (RMA).
    """
    q_item = db.query(ZtpQueue).filter(ZtpQueue.id == item_id).first()
    if not q_item:
        raise HTTPException(status_code=404, detail="Queue item not found")

    # [RMA Swap Logic]
    if payload.swap_with_device_id:
        old_dev = db.query(Device).filter(Device.id == payload.swap_with_device_id).first()
        if not old_dev:
            raise HTTPException(404, "Target device for swap not found")
        
        logger.info("ZTP swapping old_device=%s new_serial=%s", old_dev.name, q_item.serial_number)
        
        # 1. Inherit Site & Basic Info
        q_item.assigned_site_id = old_dev.site_id
        q_item.target_hostname = old_dev.name # Re-use the old hostname
        
        # 2. Config Strategy:
        # Re-use the template assigned to the old device if available.
        # This ensures the new device gets the same role-based configuration.
        if hasattr(old_dev, 'auto_provision_template_id') and old_dev.auto_provision_template_id:
            q_item.assigned_template_id = old_dev.auto_provision_template_id
        else:
            # If no specific template was assigned, we leave it empty.
            # The admin can manually assign one later, or the device will just get basic reachability.
            q_item.assigned_template_id = None
        
        # 3. Retire Old Device
        # Rename old device to avoid collision
        old_name = old_dev.name
        old_dev.name = f"{old_name}_replaced_{datetime.now().strftime('%Y%m%d%H%M')}"
        old_dev.status = "decommissioned"
        
        
    else:
        # Standard Approval
        q_item.assigned_site_id = payload.site_id
        q_item.assigned_template_id = payload.template_id
        q_item.target_hostname = payload.target_hostname

    q_item.status = ZtpStatus.READY.value
    db.commit()
    
    # [Audit]
    audit_msg = f"Approved device {q_item.serial_number} as {q_item.target_hostname}"
    if payload.swap_with_device_id:
        audit_msg += " (RMA Swap)"
        
    AuditService.log(db, current_user, "APPROVE", "ZTP", q_item.serial_number, details=audit_msg)
    
    return {"message": "Device approved. Ready for provisioning."}
