from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from pydantic import BaseModel

from app.db.session import get_db
from app.api import deps
from app.models.user import User
from app.models.settings import SystemSetting
from app.services.email_service import EmailService

router = APIRouter()

class SettingSchema(BaseModel):
    key: str
    value: str
    description: str = None
    category: str = "General"
    class Config: from_attributes = True

class EmailTestRequest(BaseModel):
    to_email: str

class SettingUpdate(BaseModel):
    settings: Dict[str, Any]

@router.get("/general")
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer)
):
    """Get system settings. Any authenticated user can view."""
    defaults = {
        "hostname": "NetManager-Controller",
        "contact_email": "admin@local.net",
        "backup_retention_days": "30",
        "log_level": "INFO",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": "587",
        "smtp_user": "",
        "smtp_password": "",
        "smtp_from": "admin@netmanager.com",
        "default_snmp_community": "public",
        "default_ssh_username": "admin",
        "default_ssh_password": "",
        "default_enable_password": "",
        "auto_sync_enabled": "true",
        "auto_sync_interval_seconds": "3",
        "auto_sync_jitter_seconds": "0.5",
        "discovery_scope_include_cidrs": "",
        "discovery_scope_exclude_cidrs": "",
        "discovery_prefer_private": "true",
        "neighbor_crawl_scope_include_cidrs": "",
        "neighbor_crawl_scope_exclude_cidrs": "",
        "neighbor_crawl_prefer_private": "true",
        "auto_discovery_enabled": "false",
        "auto_discovery_interval_seconds": "1800",
        "auto_discovery_mode": "cidr",
        "auto_discovery_cidr": "192.168.1.0/24",
        "auto_discovery_seed_ip": "",
        "auto_discovery_seed_device_id": "",
        "auto_discovery_max_depth": "2",
        "auto_discovery_site_id": "",
        "auto_discovery_snmp_profile_id": "",
        "auto_discovery_snmp_version": "v2c",
        "auto_discovery_snmp_port": "161",
        "auto_discovery_refresh_topology": "false",
        "auto_topology_refresh_max_depth": "2",
        "auto_topology_refresh_max_devices": "200",
        "auto_topology_refresh_min_interval_seconds": "0.05",
        "auto_discovery_last_run_at": "",
        "auto_discovery_last_job_id": "",
        "auto_discovery_last_job_cidr": "",
        "auto_discovery_last_error": "",
        "auto_topology_last_run_at": "",
        "auto_topology_last_job_id": "",
        "auto_topology_last_targets": "",
        "auto_topology_last_enqueued_ok": "",
        "auto_topology_last_enqueued_fail": "",
        "auto_topology_last_error": "",
        "auto_approve_enabled": "false",
        "auto_approve_min_vendor_confidence": "0.8",
        "auto_approve_require_snmp_reachable": "true",
        "auto_approve_block_severities": "error",
        "auto_approve_trigger_topology": "false",
        "auto_approve_topology_depth": "2",
        "auto_approve_trigger_sync": "false",
        "auto_approve_trigger_monitoring": "false",
        "config_drift_enabled": "true",
        "config_drift_approval_enabled": "false",
        "topology_snapshot_auto_enabled": "true",
        "topology_snapshot_auto_scope": "site",
        "topology_snapshot_auto_interval_minutes": "60",
        "topology_snapshot_auto_change_threshold_links": "10",
        "topology_snapshot_auto_on_discovery_job_complete": "true",
        "topology_snapshot_auto_on_topology_refresh": "false",
        "config_replace_vendor_dasan_nos": '{"file_systems":["flash:","bootflash:","disk0:"],"replace_commands":["configure replace {path} force","configuration replace {path} force"],"save_commands":["write memory","copy running-config startup-config"],"copy_command_template":"copy terminal: {path}"}',
        "config_replace_vendor_ubiquoss_l2": '{"file_systems":["flash:","bootflash:","disk0:"],"replace_commands":["configure replace {path} force","configuration replace {path} force"],"save_commands":["write memory","copy running-config startup-config"],"copy_command_template":"copy terminal: {path}"}',
        "config_replace_vendor_ubiquoss_l3": '{"file_systems":["flash:","bootflash:","disk0:"],"replace_commands":["configure replace {path} force","configuration replace {path} force"],"save_commands":["write memory","copy running-config startup-config"],"copy_command_template":"copy terminal: {path}"}',
        "post_check_role_core": '["show ip bgp summary","show bgp summary","display bgp peer","show ip ospf neighbor","show ospf neighbor","display ospf peer","show lldp neighbors","show lldp neighbors detail","show clock","display clock","show version","display version","show system uptime"]',
        "post_check_role_distribution": '["show ip bgp summary","show bgp summary","display bgp peer","show ip ospf neighbor","show ospf neighbor","display ospf peer","show lldp neighbors","show clock","display clock","show version","display version","show system uptime"]',
        "post_check_role_access": '["show interfaces status","show interface status","show interfaces terse","display interface brief","show lldp neighbors","show clock","display clock","show version","display version","show system uptime"]',
        "post_check_role_edge": '["show ip route 0.0.0.0","show route 0.0.0.0","display ip routing-table 0.0.0.0","show lldp neighbors","show clock","display clock","show version","display version","show system uptime"]',
        "post_check_role_firewall": '["get system status","show system info","show clock","display clock","show version","display version","show system uptime"]',
    }
    
    settings = db.query(SystemSetting).all()
    existing_keys = {s.key for s in settings}
    
    for k, v in defaults.items():
        if k not in existing_keys:
            category = "General"
            description = "Default setting"
            if k.startswith("post_check_"):
                category = "post_check"
                description = "Default post-check profile"
            new_setting = SystemSetting(key=k, value=v, description=description, category=category)
            db.add(new_setting)
            db.commit()
    
    all_settings = db.query(SystemSetting).all()
    # Mask smtp password for safety
    result = {s.key: s.value for s in all_settings}
    if "smtp_password" in result and result["smtp_password"]:
        result["smtp_password"] = "********"
    if "default_ssh_password" in result and result["default_ssh_password"]:
        result["default_ssh_password"] = "********"
    if "default_enable_password" in result and result["default_enable_password"]:
        result["default_enable_password"] = "********"
    
    return result

@router.put("/general")
def update_settings(
    update: SettingUpdate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin)
):
    """Update system settings (Admin only)."""
    updated_count = 0
    for key, value in update.settings.items():
        # Prevent updating with masked value
        if key in ["smtp_password", "default_ssh_password", "default_enable_password"] and value == "********":
            continue
            
        setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if setting:
            setting.value = str(value)
            updated_count += 1
        else:
            new_setting = SystemSetting(key=key, value=str(value))
            db.add(new_setting)
            updated_count += 1
            
    db.commit()
    return {"message": "Settings updated", "count": updated_count}

@router.post("/test-email")
def test_email(
    req: EmailTestRequest, 
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin)
):
    """Send a test email (Admin only)."""
    result = EmailService.send_email(
        db, 
        to_email=req.to_email, 
        subject="[NetManager] Test Email", 
        content="This is a test email from your SDN Controller. Notification system is working!"
    )
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['error'])
    return {"message": "Email sent successfully"}
