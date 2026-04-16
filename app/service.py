from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Prompt, PromptVersion


def create_prompt(db: Session, name: str, description: str, tags: str, content: str) -> Prompt:
    prompt = Prompt(name=name, description=description, tags=tags)
    db.add(prompt)
    db.flush()
    version = PromptVersion(prompt_id=prompt.id, version=1, content=content)
    db.add(version)
    db.commit()
    db.refresh(prompt)
    return prompt


def get_prompt(db: Session, prompt_id: int) -> Prompt | None:
    stmt = (
        select(Prompt)
        .where(Prompt.id == prompt_id)
        .options(selectinload(Prompt.versions))
    )
    return db.scalars(stmt).first()


def get_prompt_by_name(db: Session, name: str) -> Prompt | None:
    stmt = (
        select(Prompt)
        .where(Prompt.name == name)
        .options(selectinload(Prompt.versions))
    )
    return db.scalars(stmt).first()


def list_prompts(
    db: Session,
    tag: str | None = None,
    search: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Prompt]:
    stmt = select(Prompt).options(selectinload(Prompt.versions))
    if tag:
        stmt = stmt.where(Prompt.tags.contains(tag))
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(Prompt.name.ilike(pattern) | Prompt.description.ilike(pattern))
    stmt = stmt.offset(skip).limit(limit).order_by(Prompt.updated_at.desc())
    return list(db.scalars(stmt).all())


def update_prompt(db: Session, prompt: Prompt, description: str | None, tags: str | None) -> Prompt:
    if description is not None:
        prompt.description = description
    if tags is not None:
        prompt.tags = tags
    db.commit()
    db.refresh(prompt)
    return prompt


def delete_prompt(db: Session, prompt: Prompt) -> None:
    db.delete(prompt)
    db.commit()


def add_version(db: Session, prompt: Prompt, content: str, change_note: str = "") -> PromptVersion:
    latest = max((v.version for v in prompt.versions), default=0)
    version = PromptVersion(
        prompt_id=prompt.id,
        version=latest + 1,
        content=content,
        change_note=change_note,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


def get_version(db: Session, prompt_id: int, version_num: int) -> PromptVersion | None:
    stmt = select(PromptVersion).where(
        PromptVersion.prompt_id == prompt_id,
        PromptVersion.version == version_num,
    )
    return db.scalars(stmt).first()
