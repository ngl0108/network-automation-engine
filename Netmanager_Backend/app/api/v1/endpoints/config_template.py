from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.config_template import ConfigTemplate
from app.schemas.config_template import ConfigTemplateCreate, ConfigTemplateUpdate, ConfigTemplateResponse
from typing import List

router = APIRouter()

@router.post("/", response_model=ConfigTemplateResponse)
def create_template(template: ConfigTemplateCreate, db: Session = Depends(get_db)):
    db_template = ConfigTemplate(**template.dict())
    db.add(db_template)
    db.commit()
    db.refresh(db_template)
    return db_template

@router.get("/", response_model=List[ConfigTemplateResponse])
def get_templates(db: Session = Depends(get_db)):
    return db.query(ConfigTemplate).all()

@router.get("/{template_id}", response_model=ConfigTemplateResponse)
def get_template(template_id: int, db: Session = Depends(get_db)):
    template = db.query(ConfigTemplate).filter(ConfigTemplate.id == template_id).first()
    if not template:
        raise HTTPException(404, "템플릿 없음")
    return template

@router.put("/{template_id}", response_model=ConfigTemplateResponse)
def update_template(template_id: int, update: ConfigTemplateUpdate, db: Session = Depends(get_db)):
    template = db.query(ConfigTemplate).filter(ConfigTemplate.id == template_id).first()
    if not template:
        raise HTTPException(404, "템플릿 없음")
    for key, value in update.dict(exclude_unset=True).items():
        setattr(template, key, value)
    db.commit()
    db.refresh(template)
    return template

@router.delete("/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db)):
    template = db.query(ConfigTemplate).filter(ConfigTemplate.id == template_id).first()
    if not template:
        raise HTTPException(404, "템플릿 없음")
    db.delete(template)
    db.commit()
    return {"message": "삭제 완료"}