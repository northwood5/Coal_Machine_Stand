"""项目数据库 ORM: 项目 / 方案 / 快照 三级。

- Project  项目 (如 "XX矿 12000kN 支架")
- Design   方案 (一个项目下可有多个备选方案, 各持有一份当前数据模型)
- Snapshot 版本快照 (每次计算前打快照, 支持回溯对比)
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    designs: Mapped[list["Design"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Design(Base):
    __tablename__ = "designs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    # 当前数据模型 (SupportDesignModel 的 JSON 序列化)
    model_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    project: Mapped["Project"] = relationship(back_populates="designs")
    snapshots: Mapped[list["Snapshot"]] = relationship(back_populates="design", cascade="all, delete-orphan")


class Snapshot(Base):
    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    design_id: Mapped[int] = mapped_column(ForeignKey("designs.id"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)          # 方案内递增序号
    label: Mapped[str] = mapped_column(String(256), default="")        # 如 "受力分析前自动快照"
    trigger: Mapped[str] = mapped_column(String(64), default="manual")  # manual | pre_compute | agent
    model_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    design: Mapped["Design"] = relationship(back_populates="snapshots")
