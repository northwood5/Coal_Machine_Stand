"""计算模块统一协议。

每个模块无状态、幂等: 同一数据模型快照输入必得同一输出。
这是传统模式与 Agent 模式结果一致的保证, 也是反思重试可行的前提。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from app.models.support_model import SupportDesignModel


@dataclass
class ModuleResult:
    module: str
    passed: Optional[bool]                 # None = 该模块不产生通过/不通过结论 (如运动仿真)
    results: dict = field(default_factory=dict)
    margins: dict = field(default_factory=dict)
    suggestions: list[str] = field(default_factory=list)
    standard_refs: list[str] = field(default_factory=list)
    model_updates: dict = field(default_factory=dict)   # 需写回数据模型的增量 (如 loads)


@dataclass
class FieldSpec:
    """模块输入字段描述 — 前端参数表单据此自动渲染"""
    path: str            # 数据模型中的路径, 如 "overall.working_resistance"
    label: str
    unit: str = ""
    required: bool = True


class ComputeModule(ABC):
    """六大计算模块的基类"""

    id: str = ""            # 模块标识, 如 "linkage_optimization"
    name: str = ""          # 显示名
    order: int = 0          # 主线流程中的顺序
    implemented: bool = False

    @property
    @abstractmethod
    def input_fields(self) -> list[FieldSpec]:
        """本模块需要的输入字段 (供表单渲染与完整性检查)"""

    def validate_inputs(self, model: SupportDesignModel) -> list[str]:
        """返回缺失的必填字段路径列表"""
        missing = []
        data = model.model_dump()
        for spec in self.input_fields:
            if not spec.required:
                continue
            node = data
            for part in spec.path.split("."):
                node = node.get(part) if isinstance(node, dict) else None
                if node is None:
                    break
            if node is None:
                missing.append(spec.path)
        return missing

    @abstractmethod
    def run(self, model: SupportDesignModel) -> ModuleResult:
        """执行计算。输入为数据模型快照, 不得修改传入对象。"""


class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: dict[str, ComputeModule] = {}

    def register(self, module: ComputeModule) -> None:
        self._modules[module.id] = module

    def get(self, module_id: str) -> ComputeModule:
        if module_id not in self._modules:
            raise KeyError(f"未知模块: {module_id}")
        return self._modules[module_id]

    def list_ordered(self) -> list[ComputeModule]:
        return sorted(self._modules.values(), key=lambda m: m.order)


registry = ModuleRegistry()
