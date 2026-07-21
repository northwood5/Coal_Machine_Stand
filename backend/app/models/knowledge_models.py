"""数据与知识层 ORM: 标准规范库 / 材料库 / 案例库。

标准条款结构化存储 (条款号+适用参数+限值), 校核模块精确查询;
限值类校核不走 RAG —— 必须精确命中。
"""
from typing import Optional

from sqlalchemy import JSON, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class StandardClause(Base):
    """标准规范条款 (结构化)"""
    __tablename__ = "standard_clauses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    standard_code: Mapped[str] = mapped_column(String(64))        # 如 "GB 25974.1-2010"
    clause_no: Mapped[str] = mapped_column(String(32))            # 如 "5.2.3"
    title: Mapped[str] = mapped_column(String(256))
    content: Mapped[str] = mapped_column(Text, default="")
    param_key: Mapped[str] = mapped_column(String(64), index=True)  # 校核项标识
    limit_type: Mapped[str] = mapped_column(String(16))           # min | max | range
    limit_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    limit_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(32), default="")
    module_id: Mapped[str] = mapped_column(String(64), index=True, default="")

    def ref(self) -> str:
        return f"{self.standard_code} {self.clause_no} {self.title}"


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grade: Mapped[str] = mapped_column(String(32), unique=True)   # 如 "Q690"
    yield_strength: Mapped[float] = mapped_column(Float)          # 屈服强度 MPa
    tensile_strength: Mapped[float] = mapped_column(Float)        # 抗拉强度 MPa
    elastic_modulus: Mapped[float] = mapped_column(Float, default=206000.0)  # MPa
    description: Mapped[str] = mapped_column(Text, default="")


class CaseRecord(Base):
    """历史架型案例库"""
    __tablename__ = "case_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))                # 型号
    support_type: Mapped[str] = mapped_column(String(32))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")
