from typing import Generator, List
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import jwt

from app.db.session import SessionLocal
from app.models.user import User
from app.core import config, security

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

def get_db() -> Generator:
    """Dependency for getting DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(
    db: Session = Depends(get_db), 
    token: str = Depends(oauth2_scheme)
) -> User:
    """
    Mandatory authentication dependency for ALL endpoints.
    Ensures the user is logged in and active.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Inactive user"
        )
    return user

class RoleChecker:
    """
    Simplified 3-tier RBAC Role Checker.
    Roles: admin > operator > viewer
    """
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: User = Depends(get_current_user)):
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {self.allowed_roles}. Your role: {current_user.role}"
            )
        return current_user

# =============================================================================
# 3-Tier Role System (Simplified)
# =============================================================================
# 
# 1. Admin: Full system control (User Management, Delete, Settings, All Operations)
# 2. Operator: Device management, Config deployment, ZTP approval (No Delete, No User Mgmt)
# 3. Viewer: Read-only access to Dashboards, Topology, and Logs
#
# =============================================================================

# Admin: Can do everything
require_admin = RoleChecker(["admin"])

# Operator+: Can manage devices, deploy configs, approve ZTP
require_operator = RoleChecker(["admin", "operator"])

# Viewer+: Can view dashboards, logs, topology (all authenticated users)
require_viewer = RoleChecker(["admin", "operator", "viewer"])

# Aliases for backward compatibility (map old roles to new)
require_super_admin = require_admin  # super_admin -> admin
require_network_admin = require_operator  # network_admin -> operator