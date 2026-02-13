from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.audit_service import AuditService
from typing import Optional

router = APIRouter()

@router.get("/")
def read_audit_logs(
    skip: int = 0, 
    limit: int = 100, 
    action: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get audit logs with optional filtering.
    """
    return AuditService.get_logs(db, skip, limit, filter_action=action)
