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
from app.services.variable_context_service import resolve_device_context
from difflib import unified_diff
from app.db.session import SessionLocal
from app.models.device import ConfigBackup
import uuid
from app.services.post_check_service import resolve_post_check_commands

router = APIRouter()
# Reload Trigger

def _looks_like_cli_error(output: str) -> bool:
    t = (output or "").lower()
    return any(
        s in t
        for s in (
            "% invalid",
            "invalid input",
            "unknown command",
            "unrecognized command",
            "ambiguous command",
            "incomplete command",
            "error:",
            "syntax error",
        )
    )


def _default_post_check_commands(device_type: str) -> List[str]:
    dt = str(device_type or "").lower()
    if "juniper" in dt or "junos" in dt:
        return ["show system uptime", "show system alarms", "show chassis alarms"]
    if "huawei" in dt:
        return ["display clock", "display version"]
    return ["show clock", "show version"]


def _run_post_check(conn: DeviceConnection, device_type: str, commands: List[str]) -> Dict[str, Any]:
    tried = []
    for cmd in commands:
        try:
            out = conn.send_command(cmd, read_timeout=20)
        except Exception as e:
            tried.append({"command": cmd, "ok": False, "error": f"{type(e).__name__}: {e}"})
            continue
        ok = bool(out) and not _looks_like_cli_error(out)
        if ok:
            return {"ok": True, "command": cmd, "output": out, "tried": tried}
        tried.append({"command": cmd, "ok": False, "output": out})
    return {"ok": False, "command": None, "output": None, "tried": tried}

def _deploy_worker(target: Dict[str, Any], template_content: str, opts: Dict[str, Any]):
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
            backup_id = None
            backup_error = None
            rollback_prepared = False
            rollback_ref = None
            post_check = None

            if opts.get("save_pre_backup", True):
                db_local = SessionLocal()
                try:
                    running = conn.get_running_config()
                    b = ConfigBackup(device_id=dev_id, raw_config=running, is_golden=False)
                    db_local.add(b)
                    db_local.commit()
                    db_local.refresh(b)
                    backup_id = int(b.id)
                except Exception as e:
                    try:
                        db_local.rollback()
                    except Exception:
                        pass
                    backup_error = f"{type(e).__name__}: {e}"
                finally:
                    db_local.close()

            if opts.get("prepare_device_snapshot", True):
                snap_name = f"rollback_{dev_id}_{uuid.uuid4().hex[:10]}"
                try:
                    if hasattr(conn.driver, "prepare_rollback"):
                        ok = bool(conn.driver.prepare_rollback(snap_name))
                        rollback_prepared = ok
                        rollback_ref = getattr(conn.driver, "_rollback_ref", None) or snap_name
                except Exception:
                    rollback_prepared = False
                    rollback_ref = None

            try:
                output = conn.send_config_set(config_text.splitlines())
                if opts.get("post_check_enabled", True):
                    commands = opts.get("post_check_commands") or []
                    if not commands:
                        db_local = SessionLocal()
                        try:
                            dev = db_local.query(Device).filter(Device.id == dev_id).first()
                            if dev:
                                commands = resolve_post_check_commands(db_local, dev) or []
                        finally:
                            db_local.close()
                    if not commands:
                        commands = _default_post_check_commands(info.device_type)
                    post_check = _run_post_check(conn, info.device_type, list(commands))
                    if not post_check.get("ok"):
                        raise Exception("Post-check failed")
                conn.disconnect()
                return {
                    "id": dev_id,
                    "status": "success",
                    "output": output,
                    "backup_id": backup_id,
                    "backup_error": backup_error,
                    "rollback_prepared": rollback_prepared,
                    "rollback_ref": rollback_ref,
                    "post_check": post_check,
                }
            except Exception as e:
                deploy_error = str(e)
                rollback_attempted = False
                rollback_success = False
                rollback_output = None
                rollback_error = None

                if opts.get("rollback_on_failure", True):
                    rollback_attempted = True
                    try:
                        if hasattr(conn.driver, "rollback"):
                            rollback_success = bool(conn.driver.rollback())
                        else:
                            rollback_success = False
                        rollback_output = "rollback executed" if rollback_success else "rollback not executed"
                    except Exception as re:
                        rollback_error = f"{type(re).__name__}: {re}"
                        rollback_success = False

                conn.disconnect()
                return {
                    "id": dev_id,
                    "status": "failed",
                    "error": deploy_error,
                    "backup_id": backup_id,
                    "backup_error": backup_error,
                    "rollback_attempted": rollback_attempted,
                    "rollback_success": rollback_success,
                    "rollback_output": rollback_output,
                    "rollback_error": rollback_error,
                    "rollback_prepared": rollback_prepared,
                    "rollback_ref": rollback_ref,
                    "post_check": post_check,
                }
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
    variables: Dict[str, Any] = {}


class TemplateDeployRequest(BaseModel):
    device_ids: List[int]
    variables: Dict[str, Any] = {}
    save_pre_backup: bool = True
    rollback_on_failure: bool = True
    prepare_device_snapshot: bool = True
    post_check_enabled: bool = True
    post_check_commands: List[str] = []


class TemplateDryRunRequest(BaseModel):
    device_ids: List[int]
    variables: Dict[str, Any] = {}
    include_rendered: bool = False


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

    ctx = resolve_device_context(db, device, extra=req.variables).merged
    
    missing = TemplateRenderer.validate_context(req.template_content, ctx)
    return {
        "valid": len(missing) == 0,
        "missing_variables": missing
    }

@router.post("/preview")
def preview_template(req: TemplatePreviewRequest, db: Session = Depends(get_db), current_user: User = Depends(deps.require_viewer)):
    device = db.query(Device).filter(Device.id == req.device_id).first()
    if not device: raise HTTPException(404, "Device not found")

    ctx = resolve_device_context(db, device, extra=req.variables).merged

    # Validation Check
    missing = TemplateRenderer.validate_context(req.template_content, ctx)
    if missing:
        raise HTTPException(400, f"Missing variables: {', '.join(missing)}")

    rendered = TemplateRenderer.render(req.template_content, ctx)
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
        context = resolve_device_context(db, dev, extra=req.variables).merged
        context.update({"_dev_id": dev.id})

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
            executor.submit(
                _deploy_worker,
                target,
                template.content,
                {
                    "save_pre_backup": bool(req.save_pre_backup),
                    "rollback_on_failure": bool(req.rollback_on_failure),
                    "prepare_device_snapshot": bool(req.prepare_device_snapshot),
                    "post_check_enabled": bool(req.post_check_enabled),
                    "post_check_commands": list(req.post_check_commands or []),
                },
            ): target['dev_id']
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


@router.post("/{template_id}/dry-run")
def dry_run_template(
    template_id: int,
    req: TemplateDryRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    from app.models.device import ConfigBackup

    template = db.query(ConfigTemplate).filter(ConfigTemplate.id == template_id).first()
    if not template:
        raise HTTPException(404, "Template not found")

    results = []
    for dev_id in req.device_ids:
        dev = db.query(Device).filter(Device.id == dev_id).first()
        if not dev:
            continue

        ctx = resolve_device_context(db, dev, extra=req.variables).merged
        missing = TemplateRenderer.validate_context(template.content, ctx)
        if missing:
            results.append(
                {
                    "device_id": dev.id,
                    "device_name": dev.name,
                    "status": "missing_variables",
                    "missing_variables": missing,
                    "diff_lines": [],
                }
            )
            continue

        rendered = TemplateRenderer.render(template.content, ctx)
        latest = (
            db.query(ConfigBackup)
            .filter(ConfigBackup.device_id == dev.id)
            .order_by(ConfigBackup.created_at.desc())
            .first()
        )
        old = (latest.raw_config or "") if latest else ""

        diff_lines = list(
            unified_diff(
                old.splitlines(),
                rendered.splitlines(),
                fromfile="current",
                tofile="rendered",
                lineterm="",
            )
        )

        payload = {
            "device_id": dev.id,
            "device_name": dev.name,
            "status": "ok",
            "missing_variables": [],
            "diff_lines": diff_lines,
        }
        if req.include_rendered:
            payload["rendered_config"] = rendered
        results.append(payload)

    return {"summary": results}
