"""LLM 设置存储与适配器工厂。

测试阶段非私有化部署: 用户在设置页自带 API Key。
Key 存服务端 DB (20 人内部测试可接受; 生产环境应改为加密存储/密钥管理服务)。
"""
from typing import Optional

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, Session

from app.db import Base
from app.llm.base import LLMAdapter, LLMNotConfigured


class LLMSettings(Base):
    __tablename__ = "llm_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    provider: Mapped[str] = mapped_column(String(32), default="anthropic")   # anthropic | openai_compat
    model: Mapped[str] = mapped_column(String(128), default="")
    base_url: Mapped[str] = mapped_column(String(256), default="")
    api_key: Mapped[str] = mapped_column(String(512), default="")


def get_settings(db: Session) -> LLMSettings:
    row = db.get(LLMSettings, 1)
    if row is None:
        row = LLMSettings(id=1)
        db.add(row)
        db.commit()
    return row


def save_settings(db: Session, provider: str, model: str, base_url: str,
                  api_key: Optional[str]) -> LLMSettings:
    row = get_settings(db)
    row.provider = provider
    row.model = model
    row.base_url = base_url
    if api_key:                    # 空值表示保留原 key
        row.api_key = api_key
    db.commit()
    return row


def build_adapter(db: Session) -> LLMAdapter:
    """按设置构建适配器; 未配置时抛 LLMNotConfigured"""
    s = get_settings(db)
    if not s.api_key:
        raise LLMNotConfigured("尚未配置 LLM API Key, 请在设置页填写")
    if s.provider == "anthropic":
        from app.llm.anthropic_adapter import AnthropicAdapter
        return AnthropicAdapter(api_key=s.api_key, model=s.model, base_url=s.base_url)
    if s.provider == "openai_compat":
        from app.llm.openai_compat_adapter import OpenAICompatAdapter
        return OpenAICompatAdapter(api_key=s.api_key, model=s.model, base_url=s.base_url)
    raise LLMNotConfigured(f"未知 provider: {s.provider}")
