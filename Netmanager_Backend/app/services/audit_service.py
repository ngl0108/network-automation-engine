from sqlalchemy.orm import Session
from app.models.audit import AuditLog
import json
from typing import Any
import logging

logger = logging.getLogger(__name__)

class AuditService:
    @staticmethod
    def log(db: Session, user: Any, action: str, resource_type: str, resource_name: str, details: str = None, status: str = "success", ip: str = None):
        """
        Write an audit log entry.
        """
        try:
            # Try to extract user info safely
            user_id = getattr(user, 'id', None)
            username = getattr(user, 'username', 'system') if user else 'system'
            
            # If details is a dict/list, convert to string
            if isinstance(details, (dict, list)):
                details = json.dumps(details, default=str)

            log_entry = AuditLog(
                user_id=user_id,
                username=username,
                action=action,
                resource_type=resource_type,
                resource_name=resource_name,
                details=details,
                status=status,
                ip_address=ip
            )
            db.add(log_entry)
            db.commit()
        except Exception as e:
            logger.exception("Failed to write audit log")
            # db.rollback() # Don't rollback main transaction if audit fails? Or maybe create new session? 
            # Ideally audit should be safe.

    @staticmethod
    def get_logs(db: Session, skip: int = 0, limit: int = 100, filter_action: str = None):
        query = db.query(AuditLog)
        if filter_action and filter_action != 'all':
            query = query.filter(AuditLog.action == filter_action)
        return query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit).all()
