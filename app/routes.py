from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import schemas, service
from app.database import get_db

router = APIRouter(prefix="/prompts", tags=["prompts"])


def _tags_to_str(tags: list[str]) -> str:
    return ",".join(t.strip() for t in tags if t.strip())


def _tags_to_list(tags_str: str) -> list[str]:
    return [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []


def _prompt_to_out(prompt) -> schemas.PromptOut:
    latest = max(prompt.versions, key=lambda v: v.version) if prompt.versions else None
    return schemas.PromptOut(
        id=prompt.id,
        name=prompt.name,
        description=prompt.description,
        tags=_tags_to_list(prompt.tags),
        created_at=prompt.created_at,
        updated_at=prompt.updated_at,
        latest_version=schemas.PromptVersionOut.model_validate(latest) if latest else None,
    )


def _prompt_to_detail(prompt) -> schemas.PromptDetail:
    latest = max(prompt.versions, key=lambda v: v.version) if prompt.versions else None
    return schemas.PromptDetail(
        id=prompt.id,
        name=prompt.name,
        description=prompt.description,
        tags=_tags_to_list(prompt.tags),
        created_at=prompt.created_at,
        updated_at=prompt.updated_at,
        latest_version=schemas.PromptVersionOut.model_validate(latest) if latest else None,
        versions=[schemas.PromptVersionOut.model_validate(v) for v in prompt.versions],
    )


@router.post("", response_model=schemas.PromptOut, status_code=201)
def create_prompt(body: schemas.PromptCreate, db: Session = Depends(get_db)):
    existing = service.get_prompt_by_name(db, body.name)
    if existing:
        raise HTTPException(status_code=409, detail="Prompt with this name already exists")
    prompt = service.create_prompt(
        db, name=body.name, description=body.description,
        tags=_tags_to_str(body.tags), content=body.content,
    )
    return _prompt_to_out(prompt)


@router.get("", response_model=list[schemas.PromptOut])
def list_prompts(
    tag: str | None = Query(None),
    search: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    prompts = service.list_prompts(db, tag=tag, search=search, skip=skip, limit=limit)
    return [_prompt_to_out(p) for p in prompts]


@router.get("/{prompt_id}", response_model=schemas.PromptDetail)
def get_prompt(prompt_id: int, db: Session = Depends(get_db)):
    prompt = service.get_prompt(db, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return _prompt_to_detail(prompt)


@router.patch("/{prompt_id}", response_model=schemas.PromptOut)
def update_prompt(prompt_id: int, body: schemas.PromptUpdate, db: Session = Depends(get_db)):
    prompt = service.get_prompt(db, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    tags_str = _tags_to_str(body.tags) if body.tags is not None else None
    prompt = service.update_prompt(db, prompt, description=body.description, tags=tags_str)
    return _prompt_to_out(prompt)


@router.delete("/{prompt_id}", status_code=204)
def delete_prompt(prompt_id: int, db: Session = Depends(get_db)):
    prompt = service.get_prompt(db, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    service.delete_prompt(db, prompt)


# --- Version endpoints ---

@router.post("/{prompt_id}/versions", response_model=schemas.PromptVersionOut, status_code=201)
def create_version(prompt_id: int, body: schemas.PromptVersionCreate, db: Session = Depends(get_db)):
    prompt = service.get_prompt(db, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    version = service.add_version(db, prompt, content=body.content, change_note=body.change_note)
    return schemas.PromptVersionOut.model_validate(version)


@router.get("/{prompt_id}/versions/{version_num}", response_model=schemas.PromptVersionOut)
def get_version(prompt_id: int, version_num: int, db: Session = Depends(get_db)):
    version = service.get_version(db, prompt_id, version_num)
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    return schemas.PromptVersionOut.model_validate(version)
