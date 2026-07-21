"""统一支架参数化数据模型 (SupportDesignModel)

纵向贯穿各层的数据总线。所有模块间不直接传递散装参数,
只传递本模型的快照与增量。

脏标记机制: 上游参数变更后, 下游派生数据 (loads / checks) 自动标脏,
Agent 与传统模式据此判断哪些结果需要重算。
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DesignStatus(str, Enum):
    DRAFT = "draft"            # 设计中
    CHECKING = "checking"      # 校核中
    COMPLETED = "completed"    # 已完成


class SupportType(str, Enum):
    """架型"""
    SHIELD_2LEG = "shield_2leg"        # 两柱掩护式
    SHIELD_4LEG = "shield_4leg"        # 四柱支撑掩护式
    CHOCK = "chock"                    # 支撑式
    END = "end"                        # 端头支架
    TRANSITION = "transition"          # 过渡支架


class Meta(BaseModel):
    """基本信息"""
    name: str = ""                                  # 型号名称, 如 ZY12000/24/50D
    support_type: SupportType = SupportType.SHIELD_2LEG
    status: DesignStatus = DesignStatus.DRAFT
    description: str = ""


class OverallParams(BaseModel):
    """总体参数 (用户输入)"""
    height_min: Optional[float] = Field(None, description="最低支撑高度 mm")
    height_max: Optional[float] = Field(None, description="最高支撑高度 mm")
    working_resistance: Optional[float] = Field(None, description="工作阻力 kN")
    setting_load: Optional[float] = Field(None, description="初撑力 kN")
    center_distance: Optional[float] = Field(None, description="支架中心距 mm")
    width_min: Optional[float] = Field(None, description="最小宽度 mm")
    width_max: Optional[float] = Field(None, description="最大宽度 mm")
    support_strength: Optional[float] = Field(None, description="支护强度 MPa")
    floor_pressure_max: Optional[float] = Field(None, description="对底板最大比压 MPa")
    pump_pressure: Optional[float] = Field(None, description="泵站压力 MPa")


class LinkageParams(BaseModel):
    """四连杆机构参数 (构型设计模块写入/用户输入)"""
    front_link_length: Optional[float] = Field(None, description="前连杆长度 mm")
    rear_link_length: Optional[float] = Field(None, description="后连杆长度 mm")
    shield_beam_length: Optional[float] = Field(None, description="掩护梁长度(顶梁铰点E到后连杆上铰点C) mm")
    shield_top_to_front_hinge: Optional[float] = Field(None, description="顶梁铰点E到前连杆上铰点D距离 mm")
    # 铰点坐标 (底座坐标系, mm)
    front_link_lower_hinge: Optional[tuple[float, float]] = Field(None, description="前连杆下铰点 (x,y)")
    rear_link_lower_hinge: Optional[tuple[float, float]] = Field(None, description="后连杆下铰点 (x,y)")
    front_link_upper_hinge: Optional[tuple[float, float]] = Field(None, description="前连杆上铰点 (x,y)")
    rear_link_upper_hinge: Optional[tuple[float, float]] = Field(None, description="后连杆上铰点 (x,y)")
    # 优化目标与约束
    lemniscate_width_limit: Optional[float] = Field(None, description="双纽线宽度允许值 mm")
    # 顶梁与立柱布置 (受力分析用)
    canopy_length: Optional[float] = Field(None, description="顶梁长度 mm")
    leg_hinge_x: Optional[float] = Field(None, description="立柱柱窝距顶梁铰点水平距离 mm")
    leg_count: Optional[int] = Field(2, description="立柱数量")


class SectionParams(BaseModel):
    """截面参数 (用户输入/优化建议)"""
    canopy_web_thickness: Optional[float] = Field(None, description="顶梁腹板厚 mm")
    canopy_flange_thickness: Optional[float] = Field(None, description="顶梁盖板厚 mm")
    canopy_height: Optional[float] = Field(None, description="顶梁截面高度 mm")
    shield_web_thickness: Optional[float] = Field(None, description="掩护梁腹板厚 mm")
    shield_flange_thickness: Optional[float] = Field(None, description="掩护梁盖板厚 mm")
    base_web_thickness: Optional[float] = Field(None, description="底座腹板厚 mm")
    link_section_width: Optional[float] = Field(None, description="连杆截面宽 mm")
    link_section_height: Optional[float] = Field(None, description="连杆截面高 mm")
    canopy_section_width: Optional[float] = Field(None, description="顶梁主筋板箱形截面宽 mm")
    leg_cylinder_bore: Optional[float] = Field(None, description="立柱缸径 mm")
    leg_rod_diameter: Optional[float] = Field(None, description="立柱活塞杆径 mm")
    leg_wall_thickness: Optional[float] = Field(None, description="立柱缸体壁厚 mm")
    material_grade: Optional[str] = Field(None, description="主体材料牌号, 如 Q690")
    leg_material_grade: Optional[str] = Field(None, description="立柱缸体材料, 如 27SiMn")


class LoadCase(BaseModel):
    """单个工况的载荷结果 (受力分析模块写入, 校核模块只读)"""
    case_name: str                                   # 工况名, 如 "顶梁端部加载"
    description: str = ""
    leg_force: Optional[float] = None                # 立柱力 kN
    front_link_force: Optional[float] = None         # 前连杆力 kN (拉正压负)
    rear_link_force: Optional[float] = None          # 后连杆力 kN
    canopy_moment_max: Optional[float] = None        # 顶梁最大弯矩 kN·m
    shield_moment_max: Optional[float] = None        # 掩护梁最大弯矩 kN·m
    extra: dict = Field(default_factory=dict)        # 模块自定义扩展


class LoadData(BaseModel):
    """载荷数据 (受力分析模块写入)"""
    dirty: bool = True                               # 上游参数变更后标脏
    computed_at: Optional[datetime] = None
    height_analyzed: Optional[float] = None          # 分析时的支撑高度 mm
    cases: list[LoadCase] = Field(default_factory=list)


class CheckResult(BaseModel):
    """单个模块的校核结果"""
    module: str                                      # 模块标识, 如 "structure_check"
    dirty: bool = True
    passed: Optional[bool] = None
    computed_at: Optional[datetime] = None
    safety_factors: dict[str, float] = Field(default_factory=dict)   # 各校核项安全系数
    margins: dict[str, float] = Field(default_factory=dict)          # 各校核项裕度
    standard_refs: list[str] = Field(default_factory=list)           # 对标条款, 如 "GB 25974.1-2010 5.2.3"
    suggestions: list[str] = Field(default_factory=list)
    detail: dict = Field(default_factory=dict)


class SupportDesignModel(BaseModel):
    """统一支架参数化数据模型 — 唯一事实来源"""
    meta: Meta = Field(default_factory=Meta)
    overall: OverallParams = Field(default_factory=OverallParams)
    linkage: LinkageParams = Field(default_factory=LinkageParams)
    sections: SectionParams = Field(default_factory=SectionParams)
    loads: LoadData = Field(default_factory=LoadData)
    checks: dict[str, CheckResult] = Field(default_factory=dict)     # key = module 标识

    # ---- 脏标记传播 ----
    # 数据血缘: overall/linkage/sections 是上游 → loads 是中游 → checks 是下游
    def mark_upstream_changed(self, section: str) -> None:
        """上游参数变更时调用, 将下游派生数据标脏。

        section: "overall" | "linkage" | "sections"
        """
        if section in ("overall", "linkage", "sections"):
            self.loads.dirty = True
            for check in self.checks.values():
                check.dirty = True

    def set_loads(self, loads: LoadData) -> None:
        """受力分析模块写入载荷; 载荷更新后所有校核结果标脏"""
        loads.dirty = False
        loads.computed_at = datetime.now(timezone.utc)
        self.loads = loads
        for check in self.checks.values():
            check.dirty = True

    def set_check(self, result: CheckResult) -> None:
        result.dirty = False
        result.computed_at = datetime.now(timezone.utc)
        self.checks[result.module] = result

    def completeness(self) -> dict[str, list[str]]:
        """参数完整性检查: 返回各区块缺失的字段名 (Agent 模式追问/传统模式表单提示共用)"""
        missing: dict[str, list[str]] = {}
        for name in ("overall", "linkage", "sections"):
            block: BaseModel = getattr(self, name)
            empty = [k for k, v in block.model_dump().items() if v is None]
            if empty:
                missing[name] = empty
        return missing
