from typing import List, Optional, Any, Dict
from pydantic import BaseModel
from datetime import datetime

class TopologyLayoutBase(BaseModel):
    name: Optional[str] = "Default Layout"
    is_shared: Optional[bool] = False
    data: List[Dict[str, Any]]  # React Flow nodes state (id, position, width, height, etc)

class TopologyLayoutCreate(TopologyLayoutBase):
    pass

class TopologyLayoutResponse(TopologyLayoutBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
