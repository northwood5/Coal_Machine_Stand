"""API 请求/响应 schema"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.support_model import SupportDesignModel


class ProjectCreate(BaseModel):
    name: str
    description: str = ""


class ProjectOut(BaseModel):
    id: int
    name: str
    description: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DesignCreate(BaseModel):
    name: str


class DesignOut(BaseModel):
    id: int
    project_id: int
    name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DesignDetail(DesignOut):
    model: SupportDesignModel


class ParamUpdate(BaseModel):
    """参数更新: section 指定区块, values 为字段增量"""
    section: str                      # meta | overall | linkage | sections
    values: dict


class SnapshotOut(BaseModel):
    id: int
    seq: int
    label: str
    trigger: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ModuleInfo(BaseModel):
    id: str
    name: str
    order: int
    implemented: bool
    input_fields: list[dict]
    missing_inputs: Optional[list[str]] = None
    dirty: Optional[bool] = None       # 该模块结果是否已过期


class ModuleRunResult(BaseModel):
    module: str
    passed: Optional[bool]
    results: dict
    margins: dict
    suggestions: list[str]
    standard_refs: list[str]
    snapshot_id: int                   # 计算前自动快照
