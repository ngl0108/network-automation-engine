from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base

class TopologyLayout(Base):
    __tablename__ = "topology_layout"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False, default="Default Layout")
    data = Column(JSON, nullable=False)  # Stores node positions, sizes, etc.
    is_shared = Column(Boolean, default=False)  # Allow sharing with other users (future)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship (User model needs backref to access layouts if needed)
    user = relationship("User", backref="layouts")
