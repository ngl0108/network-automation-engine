from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ConfigTemplateBase(BaseModel):
    name: str
    description: Optional[str] = None
    template_text: str

class ConfigTemplateCreate(ConfigTemplateBase):
    pass

class ConfigTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    template_text: Optional[str] = None

class ConfigTemplateResponse(ConfigTemplateBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True