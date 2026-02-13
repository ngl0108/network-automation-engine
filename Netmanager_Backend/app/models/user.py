from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base

class User(Base):
    __tablename__ = "users"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    role = Column(String, default="viewer") # admin, editor, viewer
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime(timezone=True), nullable=True)
    
    # [Security] First Run Wizard Fields
    eula_accepted = Column(Boolean, default=False)
    must_change_password = Column(Boolean, default=True) # Forced change for new users
    
    # Relationship to Device (Device owner)
    devices = relationship("Device", back_populates="owner")

from app.models import device as _device
