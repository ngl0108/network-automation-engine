from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.log import EventLog
from typing import List

router = APIRouter()

@router.get("/", response_model=List[dict])
def get_logs(
    skip: int = 0, limit: int = 100, severity: str = None, db: Session = Depends(get_db)
):
    query = db.query(EventLog).order_by(EventLog.timestamp.desc())
    if severity:
        query = query.filter(EventLog.severity == severity.upper())
    logs = query.offset(skip).limit(limit).all()
    return [ {
        "id": log.id,
        "timestamp": log.timestamp,
        "severity": log.severity,
        "source": log.source,
        "event_id": log.event_id,
        "message": log.message
    } for log in logs ]