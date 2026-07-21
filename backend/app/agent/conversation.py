"""Agent 对话历史持久化 (每方案一份)"""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, select
from sqlalchemy.orm import Mapped, mapped_column, Session

from app.db import Base


class AgentConversation(Base):
    __tablename__ = "agent_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    design_id: Mapped[int] = mapped_column(ForeignKey("designs.id"), unique=True)
    # 中立格式消息列表 (含 tool 消息, 供 LLM 续聊)
    messages: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))


def load_history(db: Session, design_id: int) -> list[dict]:
    row = db.scalar(select(AgentConversation).where(AgentConversation.design_id == design_id))
    return list(row.messages) if row else []


def save_history(db: Session, design_id: int, messages: list[dict]) -> None:
    row = db.scalar(select(AgentConversation).where(AgentConversation.design_id == design_id))
    if row is None:
        row = AgentConversation(design_id=design_id, messages=messages)
        db.add(row)
    else:
        row.messages = messages
    db.commit()


def clear_history(db: Session, design_id: int) -> None:
    row = db.scalar(select(AgentConversation).where(AgentConversation.design_id == design_id))
    if row is not None:
        row.messages = []
        db.commit()
