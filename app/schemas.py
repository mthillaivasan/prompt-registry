from datetime import datetime

from pydantic import BaseModel


# --- Prompt Version schemas ---

class PromptVersionCreate(BaseModel):
    content: str
    change_note: str = ""


class PromptVersionOut(BaseModel):
    id: int
    version: int
    content: str
    change_note: str
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Prompt schemas ---

class PromptCreate(BaseModel):
    name: str
    description: str = ""
    tags: list[str] = []
    content: str  # initial version content


class PromptUpdate(BaseModel):
    description: str | None = None
    tags: list[str] | None = None


class PromptOut(BaseModel):
    id: int
    name: str
    description: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    latest_version: PromptVersionOut | None = None

    model_config = {"from_attributes": True}


class PromptDetail(PromptOut):
    versions: list[PromptVersionOut] = []
