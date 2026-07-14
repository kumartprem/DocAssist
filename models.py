import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def generate_token() -> str:
    return uuid.uuid4().hex[:16]


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    client_name: Mapped[str] = mapped_column(String(200))
    client_email: Mapped[str] = mapped_column(String(200))
    access_token: Mapped[str] = mapped_column(
        String(16), default=generate_token, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    checklist_items: Mapped[list["ChecklistItem"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


class ChecklistItem(Base):
    __tablename__ = "checklist_items"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_received: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    case: Mapped["Case"] = relationship(back_populates="checklist_items")
