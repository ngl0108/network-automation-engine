from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import List

from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.core import security, config
from app.api import deps

router = APIRouter()

@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """User login and JWT token generation."""
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
         raise HTTPException(status_code=400, detail="Inactive user")

    access_token_expires = timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(deps.get_current_user)):
    """Get current user information."""
    return current_user
@router.post("/me/accept-eula", response_model=UserResponse)
def accept_eula(current_user: User = Depends(deps.get_current_user), db: Session = Depends(get_db)):
    """User accepts EULA."""
    current_user = db.merge(current_user) # Fix: merge into current session
    current_user.eula_accepted = True
    db.commit()
    db.refresh(current_user)
    return current_user

@router.post("/me/change-password", response_model=UserResponse)
def change_password_me(
    new_password: str, 
    current_password: str,
    current_user: User = Depends(deps.get_current_user), 
    db: Session = Depends(get_db)
):
    """Change own password and clear 'must_change_password' flag."""
    current_user = db.merge(current_user) # Fix: merge into current session

    if not security.verify_password(current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect current password")
    
    current_user.hashed_password = security.get_password_hash(new_password)
    current_user.must_change_password = False
    db.commit()
    db.refresh(current_user)
    return current_user


# --- Administrative Endpoints (Admin Only) ---

@router.post("/users", response_model=UserResponse, dependencies=[Depends(deps.require_super_admin)])
def create_user(user_in: UserCreate, db: Session = Depends(get_db)):
    """Create a new user (Admin only)."""
    db_user = db.query(User).filter(User.username == user_in.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_password = security.get_password_hash(user_in.password)
    new_user = User(
        username=user_in.username,
        email=user_in.email,
        hashed_password=hashed_password,
        full_name=user_in.full_name,
        role=user_in.role,
        is_active=user_in.is_active
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.get("/users", response_model=List[UserResponse], dependencies=[Depends(deps.require_super_admin)])
def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Read all users (Admin only)."""
    users = db.query(User).offset(skip).limit(limit).all()
    return users

@router.put("/users/{user_id}", response_model=UserResponse, dependencies=[Depends(deps.require_super_admin)])
def update_user(user_id: int, user_in: UserUpdate, db: Session = Depends(get_db)):
    """Update a user (Admin only)."""
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    update_data = user_in.dict(exclude_unset=True)
    if "password" in update_data:
        update_data["hashed_password"] = security.get_password_hash(update_data.pop("password"))
    
    for field, value in update_data.items():
        setattr(db_user, field, value)
    
    db.commit()
    db.refresh(db_user)
    return db_user

@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(deps.require_super_admin)])
def delete_user(user_id: int, db: Session = Depends(get_db)):
    """Delete a user (Admin only)."""
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db.delete(db_user)
    db.commit()
    return None
