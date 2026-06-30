"""ORM model for the shared prompt library (workspace-scoped)."""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ..models import _now


def _uuid() -> str:
    return uuid4().hex


class PromptRow(Base):
    __tablename__ = "prompts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    author_id: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text)
    # Tags are stored as a JSON array string; the workspace scale is small, so
    # search filters in Python rather than needing a join table.
    tags: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(default=_now)
