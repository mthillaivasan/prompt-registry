"""Component and template library endpoints."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import PromptComponent, PromptTemplate, User

router = APIRouter(tags=["library"])


@router.get("/components")
def list_components(
    category: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(PromptComponent).filter(PromptComponent.is_active == True)  # noqa: E712
    if category:
        query = query.filter(PromptComponent.category == category)
    components = query.order_by(PromptComponent.sort_order).all()
    return [
        {
            "component_id": c.component_id,
            "code": c.code,
            "category": c.category,
            "name": c.name,
            "description": c.description,
            "component_text": c.component_text,
            "example_output": c.example_output,
            "applicable_dimensions": json.loads(c.applicable_dimensions) if c.applicable_dimensions else [],
        }
        for c in components
    ]


@router.get("/templates")
def list_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    templates = db.query(PromptTemplate).filter(PromptTemplate.is_active == True).order_by(PromptTemplate.sort_order).all()  # noqa: E712
    return [
        {
            "template_id": t.template_id,
            "code": t.code,
            "name": t.name,
            "description": t.description,
            "use_case": t.use_case,
            "prompt_type": t.prompt_type,
            "risk_tier": t.risk_tier,
            "input_type": t.input_type,
            "output_type": t.output_type,
            "component_codes": json.loads(t.component_codes) if t.component_codes else [],
            "output_example": t.output_example,
            "gold_standard_grade": t.gold_standard_grade,
            "sort_order": t.sort_order,
        }
        for t in templates
    ]


@router.get("/templates/{template_id}")
def get_template(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    t = db.query(PromptTemplate).filter(PromptTemplate.template_id == template_id).first()
    if not t:
        t = db.query(PromptTemplate).filter(PromptTemplate.code == template_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")

    codes = json.loads(t.component_codes) if t.component_codes else []
    components = db.query(PromptComponent).filter(PromptComponent.code.in_(codes)).all() if codes else []

    return {
        "template_id": t.template_id,
        "code": t.code,
        "name": t.name,
        "description": t.description,
        "use_case": t.use_case,
        "prompt_type": t.prompt_type,
        "risk_tier": t.risk_tier,
        "input_type": t.input_type,
        "output_type": t.output_type,
        "component_codes": codes,
        "output_example": t.output_example,
        "gold_standard_grade": t.gold_standard_grade,
        "components": [
            {
                "code": c.code,
                "category": c.category,
                "name": c.name,
                "description": c.description,
                "component_text": c.component_text,
                "example_output": c.example_output,
            }
            for c in components
        ],
    }
