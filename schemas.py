from datetime import datetime

from pydantic import BaseModel, EmailStr


# --- Case ---

class CaseCreate(BaseModel):
    title: str
    client_name: str
    client_email: str
    checklist_items: list[str] = []


class ChecklistItemOut(BaseModel):
    id: int
    name: str
    description: str | None
    is_received: bool
    uploaded_at: datetime | None

    model_config = {"from_attributes": True}


class CaseOut(BaseModel):
    id: int
    title: str
    client_name: str
    client_email: str
    access_token: str
    created_at: datetime
    checklist_items: list[ChecklistItemOut]

    model_config = {"from_attributes": True}


class CaseSummary(BaseModel):
    id: int
    title: str
    client_name: str
    client_email: str
    created_at: datetime
    total_items: int
    received_items: int

    model_config = {"from_attributes": True}


# --- Checklist ---

class ChecklistItemCreate(BaseModel):
    name: str
    description: str | None = None
