from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.approval import ApprovalRequest
from app.models.user import User
from app.api import deps
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

# --- Pydantic Schemas ---

class ApprovalRequestBase(BaseModel):
    title: str
    description: Optional[str] = None
    request_type: str = "config_deploy"
    payload: Optional[dict] = None # JSON Payload

class ApprovalCreate(ApprovalRequestBase):
    requester_comment: Optional[str] = None

class ApprovalDecision(BaseModel):
    approver_comment: Optional[str] = None

class ApprovalResponse(ApprovalRequestBase):
    id: int
    requester_id: int
    approver_id: Optional[int] = None
    status: str
    requester_comment: Optional[str] = None
    approver_comment: Optional[str] = None
    created_at: datetime
    decided_at: Optional[datetime] = None
    
    requester_name: Optional[str] = None # For UI convenience
    approver_name: Optional[str] = None

    class Config:
        from_attributes = True

# --- Endpoints ---

@router.post("/", response_model=ApprovalResponse)
def create_request(
    req: ApprovalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer)
):
    """
    Submit a new approval request.
    """
    db_req = ApprovalRequest(
        **req.dict(exclude={"requester_name", "approver_name"}), # Create model kwargs
        requester_id=current_user.id,
        status="pending"
    )
    db.add(db_req)
    db.commit()
    db.refresh(db_req)
    
    # Return with name (manual population or relationship load)
    res = ApprovalResponse.from_orm(db_req)
    res.requester_name = current_user.username
    return res

@router.get("/", response_model=List[ApprovalResponse])
def get_requests(
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer)
):
    """
    List approval requests. Filter by status if provided.
    """
    query = db.query(ApprovalRequest)
    
    if status:
        query = query.filter(ApprovalRequest.status == status)
        
    # Optional: Filter strictly for non-admins? usually admins can see all.
    # If standard user, maybe only see own requests?
    if current_user.role != "admin":
        query = query.filter(ApprovalRequest.requester_id == current_user.id)

    total = query.count()
    items = query.order_by(ApprovalRequest.created_at.desc()).offset(skip).limit(limit).all()

    # Populate names manually to avoid complex joins in Pydantic mapping issues
    result = []
    for item in items:
        resp = ApprovalResponse.from_orm(item)
        if item.requester: resp.requester_name = item.requester.username
        if item.approver: resp.approver_name = item.approver.username
        result.append(resp)
        
    return result

@router.get("/{id}", response_model=ApprovalResponse)
def get_request(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer)
):
    req = db.query(ApprovalRequest).filter(ApprovalRequest.id == id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
        
    # Check permission
    if current_user.role != "admin" and req.requester_id != current_user.id:
         raise HTTPException(status_code=403, detail="Not enough permissions")

    resp = ApprovalResponse.from_orm(req)
    if req.requester: resp.requester_name = req.requester.username
    if req.approver: resp.approver_name = req.approver.username
    return resp

@router.post("/{id}/approve", response_model=ApprovalResponse)
def approve_request(
    id: int,
    decision: ApprovalDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_admin)
):
    req = db.query(ApprovalRequest).filter(ApprovalRequest.id == id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
        
    if req.status != "pending":
         raise HTTPException(status_code=400, detail="Request is already decided")

    req.status = "approved"
    req.approver_id = current_user.id
    req.approver_comment = decision.approver_comment
    req.decided_at = datetime.now()
    
    db.commit()
    db.refresh(req)
    
    payload = dict(req.payload or {})
    if str(req.request_type or "") == "config_drift_remediate":
        try:
            from app.tasks.compliance import run_config_drift_remediation_for_approval

            if hasattr(run_config_drift_remediation_for_approval, "apply_async"):
                r = run_config_drift_remediation_for_approval.apply_async(
                    args=[req.id],
                    queue="maintenance",
                )
                payload["execution_status"] = "queued"
                payload["job_id"] = r.id
            else:
                result = run_config_drift_remediation_for_approval(req.id)
                payload["execution_status"] = "executed"
                payload["execution_result"] = result
            req.payload = payload
            db.commit()
            db.refresh(req)
        except Exception as e:
            payload["execution_status"] = "dispatch_failed"
            payload["dispatch_error"] = f"{type(e).__name__}: {e}"
            req.payload = payload
            db.commit()
            db.refresh(req)
    
    resp = ApprovalResponse.from_orm(req)
    if req.requester: resp.requester_name = req.requester.username
    if req.approver: resp.approver_name = req.approver.username
    return resp

@router.post("/{id}/reject", response_model=ApprovalResponse)
def reject_request(
    id: int,
    decision: ApprovalDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_admin)
):
    req = db.query(ApprovalRequest).filter(ApprovalRequest.id == id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
        
    if req.status != "pending":
         raise HTTPException(status_code=400, detail="Request is already decided")

    req.status = "rejected"
    req.approver_id = current_user.id
    req.approver_comment = decision.approver_comment
    req.decided_at = datetime.now()
    
    db.commit()
    db.refresh(req)
    
    resp = ApprovalResponse.from_orm(req)
    if req.requester: resp.requester_name = req.requester.username
    if req.approver: resp.approver_name = req.approver.username
    return resp
