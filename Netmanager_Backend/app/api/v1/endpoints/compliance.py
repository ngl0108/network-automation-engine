from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from app.db.session import get_db
from app.models.compliance import ComplianceStandard, ComplianceRule
from app.models.device import Device, ComplianceReport, ConfigBackup
from app.services.compliance_service import ComplianceEngine
from pydantic import BaseModel, ConfigDict

router = APIRouter()

# --- Pydantic Schemas ---

class RuleBase(BaseModel):
    name: str
    description: Optional[str] = None
    severity: str = "medium"
    check_type: str = "simple_match"
    pattern: str
    remediation: Optional[str] = None

class RuleCreate(RuleBase):
    pass

class RuleResponse(RuleBase):
    id: int
    standard_id: int
    model_config = ConfigDict(from_attributes=True)

class StandardBase(BaseModel):
    name: str
    description: Optional[str] = None
    device_family: str = "cisco_ios"

class StandardCreate(StandardBase):
    pass

class StandardResponse(StandardBase):
    id: int
    rules: List[RuleResponse] = []
    model_config = ConfigDict(from_attributes=True)

class ScanRequest(BaseModel):
    device_ids: List[int]
    standard_id: Optional[int] = None

# --- Endpoints ---

@router.get("/standards", response_model=List[StandardResponse])
def get_standards(db: Session = Depends(get_db)):
    return db.query(ComplianceStandard).options(joinedload(ComplianceStandard.rules)).all()

@router.post("/standards", response_model=StandardResponse)
def create_standard(standard: StandardCreate, db: Session = Depends(get_db)):
    db_std = ComplianceStandard(**standard.dict())
    db.add(db_std)
    db.commit()
    db.refresh(db_std)
    return db_std

@router.delete("/standards/{id}")
def delete_standard(id: int, db: Session = Depends(get_db)):
    std = db.query(ComplianceStandard).filter(ComplianceStandard.id == id).first()
    if not std:
        raise HTTPException(status_code=404, detail="Standard not found")
    db.delete(std)
    db.commit()
    return {"message": "Standard deleted"}

@router.post("/standards/{id}/rules", response_model=RuleResponse)
def add_rule(id: int, rule: RuleCreate, db: Session = Depends(get_db)):
    std = db.query(ComplianceStandard).filter(ComplianceStandard.id == id).first()
    if not std:
        raise HTTPException(status_code=404, detail="Standard not found")
    
    db_rule = ComplianceRule(**rule.dict(), standard_id=id)
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)
    return db_rule

@router.delete("/rules/{id}")
def delete_rule(id: int, db: Session = Depends(get_db)):
    rule = db.query(ComplianceRule).filter(ComplianceRule.id == id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()
    return {"message": "Rule deleted"}

@router.post("/scan")
def run_compliance_scan(request: ScanRequest, db: Session = Depends(get_db)):
    """
    선택된 장비들에 대해 컴플라이언스 스캔을 실행합니다.
    """
    from app.tasks.compliance import run_compliance_scan_task

    try:
        r = run_compliance_scan_task.apply_async(
            args=[request.device_ids, request.standard_id],
            queue="maintenance",
        )
        return {"job_id": r.id, "status": "queued"}
    except Exception:
        engine = ComplianceEngine(db)
        results = []
        for dev_id in request.device_ids:
            try:
                res = engine.run_rule_scan(dev_id, request.standard_id)
                results.append(res)
            except Exception as e:
                results.append({"device_id": dev_id, "error": str(e)})
        return {"job_id": None, "status": "executed", "results": results}

@router.get("/reports")
def get_reports(device_id: int = Query(None), db: Session = Depends(get_db)):
    """
    컴플라이언스 리포트를 조회합니다.
    """
    query = db.query(ComplianceReport).options(joinedload(ComplianceReport.device))
    if device_id:
        query = query.filter(ComplianceReport.device_id == device_id)
        
    reports = query.all()
    
    # JSON 응답 구성
    output = []
    for r in reports:
        output.append({
            "device_id": r.device_id,
            "device_name": r.device.name,
            "status": r.status,
            "score": r.match_percentage,
            "last_checked": r.last_checked,
            "details": r.diff_content # 임시로 diff_content에 JSON string 저장된 것 반환
        })
        
    return output


@router.get("/reports/export")
def export_reports(format: str = Query("xlsx"), device_id: int = Query(None), db: Session = Depends(get_db)):
    import io
    if format not in {"xlsx", "pdf"}:
        raise HTTPException(status_code=400, detail="Invalid format")

    query = db.query(ComplianceReport).options(joinedload(ComplianceReport.device))
    if device_id:
        query = query.filter(ComplianceReport.device_id == device_id)
    reports = query.all()

    payload = []
    for r in reports:
        payload.append(
            {
                "device_id": r.device_id,
                "device_name": r.device.name if r.device else None,
                "status": r.status,
                "score": r.match_percentage,
                "last_checked": r.last_checked.isoformat() if getattr(r, "last_checked", None) else None,
                "details": r.details if getattr(r, "details", None) else r.diff_content,
            }
        )

    from app.services.report_export_service import build_compliance_xlsx, build_compliance_pdf

    if format == "pdf":
        data = build_compliance_pdf(payload)
        media = "application/pdf"
        filename = "compliance_reports.pdf"
    else:
        data = build_compliance_xlsx(payload)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = "compliance_reports.xlsx"

    return StreamingResponse(
        io.BytesIO(data),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'},
    )

# --- Config Drift Endpoints ---

@router.get("/drift/backups/{device_id}")
def get_device_backups(device_id: int, db: Session = Depends(get_db)):
    """
    Get config backups for a device to select a Golden Config.
    """
    backups = db.query(ConfigBackup).filter(ConfigBackup.device_id == device_id)\
        .order_by(ConfigBackup.created_at.desc()).limit(20).all()
        
    return [
        {
            "id": b.id,
            "created_at": b.created_at,
            "is_golden": b.is_golden,
            "size": len(b.raw_config) if b.raw_config else 0
        }
        for b in backups
    ]

@router.post("/drift/golden/{backup_id}")
def set_golden_config(backup_id: int, db: Session = Depends(get_db)):
    """
    Set a specific backup as the Golden Config.
    """
    engine = ComplianceEngine(db)
    result = engine.set_golden_config(backup_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.get("/drift/check/{device_id}")
def check_config_drift(device_id: int, db: Session = Depends(get_db)):
    """
    Perform an immediate Config Drift Check (Golden vs Running).
    """
    engine = ComplianceEngine(db)
    result = engine.check_config_drift(device_id)
    return result
