"""六大计算模块实现。

工程说明: 本文件采用平面简化力学模型与工程常用公式,
用于总体设计阶段的方案计算与校核; 详细设计阶段应以有限元复核。
"""
from __future__ import annotations

import math

import numpy as np

from app.db import SessionLocal
from app.knowledge.seed import get_clause, get_material
from app.models.support_model import LoadCase, LoadData, SupportDesignModel
from app.modules.base import ComputeModule, FieldSpec, ModuleResult, registry
from app.modules.fourbar import (
    LinkageGeometry, lemniscate_width, optimize_linkage, pose_at_height, sweep,
)


def _geom_from_model(model: SupportDesignModel) -> LinkageGeometry | None:
    lk = model.linkage
    if None in (lk.rear_link_length, lk.front_link_length, lk.rear_link_lower_hinge,
                lk.front_link_lower_hinge, lk.shield_beam_length, lk.shield_top_to_front_hinge):
        return None
    return LinkageGeometry(
        A=tuple(lk.rear_link_lower_hinge), B=tuple(lk.front_link_lower_hinge),
        La=lk.rear_link_length, Lb=lk.front_link_length,
        lc=lk.shield_beam_length, ld=lk.shield_top_to_front_hinge,
    )


def _clause_ref(param_key: str) -> tuple[list[str], float | None, float | None]:
    """查标准条款, 返回 (引用文本, limit_min, limit_max)"""
    with SessionLocal() as db:
        clause = get_clause(db, param_key)
        if clause is None:
            return [], None, None
        return [clause.ref()], clause.limit_min, clause.limit_max


def _material(grade: str | None, default_grade: str):
    with SessionLocal() as db:
        mat = get_material(db, grade or default_grade)
        if mat is None:
            mat = get_material(db, default_grade)
        return (mat.grade, mat.yield_strength, mat.elastic_modulus) if mat else (default_grade, 690.0, 206000.0)


# ============ ① 连杆优化设计 ============

class LinkageOptimization(ComputeModule):
    id = "linkage_optimization"
    name = "连杆优化设计"
    order = 1
    implemented = True

    @property
    def input_fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("overall.height_min", "最低支撑高度", "mm"),
            FieldSpec("overall.height_max", "最高支撑高度", "mm"),
            FieldSpec("linkage.lemniscate_width_limit", "双纽线宽度允许值", "mm", required=False),
        ]

    def run(self, model: SupportDesignModel) -> ModuleResult:
        missing = self.validate_inputs(model)
        if missing:
            return ModuleResult(module=self.id, passed=None, results={"error": "missing_inputs"},
                                suggestions=[f"缺少必填参数: {', '.join(missing)}"])
        h_min, h_max = model.overall.height_min, model.overall.height_max

        geom, width, _ = optimize_linkage(h_min, h_max)

        refs, _, std_max = _clause_ref("lemniscate_width")
        limit = model.linkage.lemniscate_width_limit or std_max or 70.0
        passed = width <= limit

        return ModuleResult(
            module=self.id, passed=passed,
            results={
                "lemniscate_width": round(width, 1),
                "limit": limit,
                "geometry": {
                    "rear_link_length": round(geom.La, 1),
                    "front_link_length": round(geom.Lb, 1),
                    "rear_link_lower_hinge": [round(v, 1) for v in geom.A],
                    "front_link_lower_hinge": [round(v, 1) for v in geom.B],
                    "shield_beam_length": round(geom.lc, 1),
                    "shield_top_to_front_hinge": round(geom.ld, 1),
                },
            },
            margins={"双纽线宽度(mm)": round(width, 1)},
            standard_refs=refs,
            suggestions=[] if passed else ["双纽线宽度超限, 建议放宽高度范围或人工调整铰点后重新优化"],
            model_updates={"linkage": {
                "rear_link_length": round(geom.La, 1),
                "front_link_length": round(geom.Lb, 1),
                "rear_link_lower_hinge": [round(v, 1) for v in geom.A],
                "front_link_lower_hinge": [round(v, 1) for v in geom.B],
                "shield_beam_length": round(geom.lc, 1),
                "shield_top_to_front_hinge": round(geom.ld, 1),
            }},
        )


# ============ ② 连杆运动仿真 ============

class LinkageSimulation(ComputeModule):
    id = "linkage_simulation"
    name = "连杆运动仿真"
    order = 2
    implemented = True

    @property
    def input_fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("linkage.rear_link_length", "后连杆长度", "mm"),
            FieldSpec("linkage.front_link_length", "前连杆长度", "mm"),
            FieldSpec("linkage.rear_link_lower_hinge", "后连杆下铰点", "mm"),
            FieldSpec("linkage.front_link_lower_hinge", "前连杆下铰点", "mm"),
            FieldSpec("linkage.shield_beam_length", "掩护梁长度(E-C)", "mm"),
            FieldSpec("linkage.shield_top_to_front_hinge", "E到前连杆上铰点", "mm"),
        ]

    def run(self, model: SupportDesignModel) -> ModuleResult:
        missing = self.validate_inputs(model)
        if missing:
            return ModuleResult(module=self.id, passed=None, results={"error": "missing_inputs"},
                                suggestions=[f"缺少必填参数: {', '.join(missing)}"])
        geom = _geom_from_model(model)
        data = sweep(geom, n=100)
        if len(data["Ey"]) < 5:
            return ModuleResult(module=self.id, passed=False,
                                results={"error": "mechanism_infeasible"},
                                suggestions=["当前连杆几何无法装配, 请重新运行连杆优化"])

        results = {
            "trajectory": [[round(x, 1), round(y, 1)] for x, y in zip(data["Ex"], data["Ey"])],
            "height_range_reachable": [round(min(data["Ey"]), 1), round(max(data["Ey"]), 1)],
        }
        passed = None
        margins = {}
        h_min, h_max = model.overall.height_min, model.overall.height_max
        if h_min and h_max:
            w, _ = lemniscate_width(geom, h_min, h_max)
            if w is None:
                passed = False
                results["error"] = "height_range_not_covered"
            else:
                results["lemniscate_width"] = round(w, 1)
                margins["双纽线宽度(mm)"] = round(w, 1)
                limit = model.linkage.lemniscate_width_limit or 70.0
                passed = w <= limit
        return ModuleResult(
            module=self.id, passed=passed, results=results, margins=margins,
            suggestions=[] if passed in (None, True) else ["高度范围不可达或摆动量超限, 需调整连杆几何"],
        )


# ============ ③ 支架受力分析 ============

def _canopy_moment(P: float, x_load: float, x_hinge: float, x_leg: float) -> float:
    """顶梁弯矩 (kN·m): 铰点E与立柱柱窝双支点梁, 集中载荷 P (kN), 坐标 mm"""
    span = abs(x_leg - x_hinge)
    if span < 1:
        return 0.0
    if min(x_hinge, x_leg) <= x_load <= max(x_hinge, x_leg):
        a = abs(x_load - x_hinge)
        b = abs(x_leg - x_load)
        return P * a * b / span / 1000.0            # mm→m
    # 悬臂段: 弯矩在近端支点处
    overhang = min(abs(x_load - x_hinge), abs(x_load - x_leg))
    return P * overhang / 1000.0


class ForceAnalysis(ComputeModule):
    id = "force_analysis"
    name = "支架受力分析"
    order = 3
    implemented = True

    @property
    def input_fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("overall.working_resistance", "工作阻力", "kN"),
            FieldSpec("overall.height_max", "最高支撑高度", "mm"),
            FieldSpec("linkage.canopy_length", "顶梁长度", "mm"),
            FieldSpec("linkage.leg_hinge_x", "柱窝距顶梁铰点距离", "mm"),
            FieldSpec("linkage.rear_link_length", "后连杆长度", "mm"),
            FieldSpec("linkage.front_link_length", "前连杆长度", "mm"),
            FieldSpec("linkage.shield_beam_length", "掩护梁长度(E-C)", "mm"),
            FieldSpec("linkage.shield_top_to_front_hinge", "E到前连杆上铰点", "mm"),
        ]

    def run(self, model: SupportDesignModel) -> ModuleResult:
        missing = self.validate_inputs(model)
        if missing:
            return ModuleResult(module=self.id, passed=None, results={"error": "missing_inputs"},
                                suggestions=[f"缺少必填参数: {', '.join(missing)}"])

        geom = _geom_from_model(model)
        P = model.overall.working_resistance
        h_analyze = 0.8 * model.overall.height_max      # 典型分析高度
        pose = pose_at_height(geom, h_analyze)
        if pose is None:
            return ModuleResult(module=self.id, passed=False,
                                results={"error": "pose_unreachable", "height": h_analyze},
                                suggestions=["分析高度不可达, 检查连杆几何或先运行运动仿真"])

        E = np.array(pose["E"])
        rear_dir = np.array(pose["rear_dir"])
        front_dir = np.array(pose["front_dir"])
        C, D = np.array(pose["C"]), np.array(pose["D"])
        Lc = model.linkage.canopy_length
        x_leg = E[0] + model.linkage.leg_hinge_x
        leg_dir = np.array([0.0, 1.0])                  # 立柱近似竖直
        leg_pos = np.array([x_leg, E[1]])

        # 载荷工况: (名称, 说明, 合力作用点x, 水平分量系数)
        cases_def = [
            ("uniform", "均布载荷(合力于顶梁中部)", E[0] + 0.5 * Lc, 0.0),
            ("front_end", "顶梁端部加载", E[0] + 0.9 * Lc, 0.0),
            ("rear", "顶梁后部加载", E[0] + 0.15 * Lc, 0.0),
            ("horizontal", "带水平推力工况", E[0] + 0.5 * Lc, 0.3),
        ]

        load_cases: list[LoadCase] = []
        for cid, desc, x_load, h_coef in cases_def:
            # 载荷降额: 作用点越过柱窝后, 支护能力受立柱力矩平衡限制
            # (对 E 取矩: F_leg·x_leg ≥ P_case·x_load → P_case = P·x_leg/x_load)
            arm_load = x_load - E[0]
            arm_leg = x_leg - E[0]
            P_case = P * min(1.0, arm_leg / arm_load) if arm_load > arm_leg else P
            # 整架平衡: 未知 [F_leg, F_rear, F_front] (沿各自方向的标量)
            # 外载: 竖直 -P_case, 水平 h_coef*P_case (向采空区), 作用于 (x_load, E.y)
            ext_F = np.array([-h_coef * P_case, -P_case])
            load_pt = np.array([x_load, E[1]])
            A_mat = np.zeros((3, 3))
            A_mat[0, :] = [leg_dir[0], rear_dir[0], front_dir[0]]
            A_mat[1, :] = [leg_dir[1], rear_dir[1], front_dir[1]]
            # 力矩 (对 E 取矩, z 分量): r × F
            for j, (pt, d) in enumerate([(leg_pos, leg_dir), (C, rear_dir), (D, front_dir)]):
                r = pt - E
                A_mat[2, j] = r[0] * d[1] - r[1] * d[0]
            r_ext = load_pt - E
            b = np.array([-ext_F[0], -ext_F[1],
                          -(r_ext[0] * ext_F[1] - r_ext[1] * ext_F[0])])
            try:
                sol = np.linalg.solve(A_mat, b)
            except np.linalg.LinAlgError:
                continue
            f_leg, f_rear, f_front = sol
            m_canopy = _canopy_moment(P_case, x_load, E[0], x_leg)
            # 掩护梁弯矩: E 处铰点力对 D 取矩近似
            F_E = np.array([0.0, f_leg]) + ext_F        # 顶梁传给掩护梁的力(近似)
            r_ed = E - D
            m_shield = abs(r_ed[0] * F_E[1] - r_ed[1] * F_E[0]) / 1000.0  # kN·mm → kN·m
            load_cases.append(LoadCase(
                case_name=cid, description=desc,
                leg_force=round(float(f_leg), 1),
                rear_link_force=round(float(f_rear), 1),
                front_link_force=round(float(f_front), 1),
                canopy_moment_max=round(m_canopy, 1),
                shield_moment_max=round(abs(m_shield), 1),
                extra={"load_x": round(float(x_load), 1), "horizontal_coef": h_coef,
                       "applied_load_kN": round(float(P_case), 1)},
            ))

        if not load_cases:
            return ModuleResult(module=self.id, passed=False, results={"error": "singular_system"},
                                suggestions=["力学方程奇异, 检查连杆几何"])

        loads = LoadData(height_analyzed=h_analyze, cases=load_cases)
        summary = {
            "height_analyzed": round(h_analyze, 1),
            "leg_force_max": max(abs(c.leg_force) for c in load_cases),
            "canopy_moment_max": max(c.canopy_moment_max for c in load_cases),
            "cases": [c.model_dump() for c in load_cases],
        }
        return ModuleResult(
            module=self.id, passed=None, results=summary,
            model_updates={"loads": loads.model_dump(mode="json")},
        )


# ============ ④ 结构件强度校核 ============

def _box_modulus(B: float, H: float, tw: float, tf: float) -> float:
    """箱形截面抗弯模量 W (mm³)"""
    b_in = max(B - 2 * tw, 1.0)
    h_in = max(H - 2 * tf, 1.0)
    return (B * H ** 3 - b_in * h_in ** 3) / (6 * H)


class StructureCheck(ComputeModule):
    id = "structure_check"
    name = "结构件强度校核"
    order = 4
    implemented = True

    @property
    def input_fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("sections.canopy_web_thickness", "顶梁腹板厚", "mm"),
            FieldSpec("sections.canopy_flange_thickness", "顶梁盖板厚", "mm"),
            FieldSpec("sections.canopy_height", "顶梁截面高", "mm"),
            FieldSpec("sections.canopy_section_width", "箱形截面宽", "mm"),
            FieldSpec("sections.link_section_width", "连杆截面宽", "mm"),
            FieldSpec("sections.link_section_height", "连杆截面高", "mm"),
            FieldSpec("sections.material_grade", "材料牌号"),
        ]

    def run(self, model: SupportDesignModel) -> ModuleResult:
        missing = self.validate_inputs(model)
        if missing:
            return ModuleResult(module=self.id, passed=None, results={"error": "missing_inputs"},
                                suggestions=[f"缺少必填参数: {', '.join(missing)}"])
        if model.loads.dirty or not model.loads.cases:
            return ModuleResult(module=self.id, passed=None, results={"error": "loads_dirty"},
                                suggestions=["载荷数据缺失或已过期, 请先运行[支架受力分析]"])

        sec = model.sections
        grade, fy, _ = _material(sec.material_grade, "Q690")
        refs, n_req, _ = _clause_ref("structure_safety_factor")
        n_req = n_req or 1.5
        allow = fy / n_req

        m_canopy = max(c.canopy_moment_max or 0 for c in model.loads.cases)      # kN·m
        m_shield = max(c.shield_moment_max or 0 for c in model.loads.cases)
        f_link = max(max(abs(c.front_link_force or 0), abs(c.rear_link_force or 0))
                     for c in model.loads.cases)                                  # kN

        # 顶梁 (双主筋板承担, 各半)
        W = _box_modulus(sec.canopy_section_width, sec.canopy_height,
                         sec.canopy_web_thickness, sec.canopy_flange_thickness)
        sigma_canopy = (m_canopy / 2) * 1e6 / W                                   # MPa
        # 掩护梁 (截面沿用顶梁参数或专用板厚)
        tw_s = sec.shield_web_thickness or sec.canopy_web_thickness
        tf_s = sec.shield_flange_thickness or sec.canopy_flange_thickness
        W_s = _box_modulus(sec.canopy_section_width, sec.canopy_height, tw_s, tf_s)
        sigma_shield = (m_shield / 2) * 1e6 / W_s
        # 连杆 (箱形, 壁厚取 0.2*短边 的简化)
        t_link = 0.2 * min(sec.link_section_width, sec.link_section_height)
        A_link = (sec.link_section_width * sec.link_section_height
                  - (sec.link_section_width - 2 * t_link) * (sec.link_section_height - 2 * t_link))
        sigma_link = f_link * 1000 / A_link

        items = {
            "顶梁弯曲": sigma_canopy,
            "掩护梁弯曲": sigma_shield,
            "连杆拉压": sigma_link,
        }
        margins = {k: round(fy / v, 2) if v > 0 else 99.0 for k, v in items.items()}
        passed = all(n >= n_req for n in margins.values())
        suggestions = [f"[{k}] 安全系数 {n} < {n_req}, 建议增大板厚或提高材料等级"
                       for k, n in margins.items() if n < n_req]
        return ModuleResult(
            module=self.id, passed=passed,
            results={"material": grade, "allowable_stress": round(allow, 1),
                     "stresses_MPa": {k: round(v, 1) for k, v in items.items()},
                     "required_safety_factor": n_req},
            margins=margins, standard_refs=refs, suggestions=suggestions,
        )


# ============ ⑤ 立柱千斤强度校核 ============

class LegJackCheck(ComputeModule):
    id = "leg_jack_check"
    name = "立柱千斤强度校核"
    order = 5
    implemented = True

    @property
    def input_fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("sections.leg_cylinder_bore", "立柱缸径", "mm"),
            FieldSpec("sections.leg_rod_diameter", "活塞杆径", "mm"),
            FieldSpec("sections.leg_wall_thickness", "缸体壁厚", "mm"),
            FieldSpec("overall.height_max", "最高支撑高度", "mm"),
        ]

    def run(self, model: SupportDesignModel) -> ModuleResult:
        missing = self.validate_inputs(model)
        if missing:
            return ModuleResult(module=self.id, passed=None, results={"error": "missing_inputs"},
                                suggestions=[f"缺少必填参数: {', '.join(missing)}"])
        if model.loads.dirty or not model.loads.cases:
            return ModuleResult(module=self.id, passed=None, results={"error": "loads_dirty"},
                                suggestions=["载荷数据缺失或已过期, 请先运行[支架受力分析]"])

        sec = model.sections
        n_leg = model.linkage.leg_count or 2
        f_leg_total = max(abs(c.leg_force or 0) for c in model.loads.cases)   # kN
        f_leg = f_leg_total / n_leg

        D, d, t = sec.leg_cylinder_bore, sec.leg_rod_diameter, sec.leg_wall_thickness
        grade, fy, E_mod = _material(sec.leg_material_grade, "27SiMn")

        # 工作压强与试验压强 (型式试验 1.5 倍)
        p_work = f_leg * 1000 / (math.pi / 4 * D ** 2)          # MPa
        p_test = 1.5 * p_work
        # 缸体环向应力 (薄壁近似)
        sigma_hoop = p_test * D / (2 * t)
        refs_c, n_cyl_req, _ = _clause_ref("leg_cylinder_safety_factor")
        n_cyl_req = n_cyl_req or 1.5
        n_cyl = fy / sigma_hoop if sigma_hoop > 0 else 99.0

        # 活塞杆压杆稳定 (欧拉, 计算长度取 0.6*最大高度, 两端铰支)
        L_buck = 0.6 * model.overall.height_max
        I_rod = math.pi * d ** 4 / 64
        P_cr = math.pi ** 2 * E_mod * I_rod / (L_buck ** 2) / 1000  # kN
        refs_b, n_buck_req, _ = _clause_ref("leg_buckling_safety_factor")
        n_buck_req = n_buck_req or 2.0
        n_buck = P_cr / f_leg if f_leg > 0 else 99.0

        margins = {"缸体强度": round(n_cyl, 2), "压杆稳定": round(n_buck, 2)}
        passed = n_cyl >= n_cyl_req and n_buck >= n_buck_req
        suggestions = []
        if n_cyl < n_cyl_req:
            suggestions.append(f"缸体安全系数 {n_cyl:.2f} < {n_cyl_req}, 建议增大壁厚")
        if n_buck < n_buck_req:
            suggestions.append(f"稳定性安全系数 {n_buck:.2f} < {n_buck_req}, 建议增大活塞杆径")
        return ModuleResult(
            module=self.id, passed=passed,
            results={"material": grade, "leg_force_kN": round(f_leg, 1),
                     "work_pressure_MPa": round(p_work, 2),
                     "test_pressure_MPa": round(p_test, 2),
                     "hoop_stress_MPa": round(sigma_hoop, 1),
                     "euler_critical_kN": round(P_cr, 1)},
            margins=margins, standard_refs=refs_c + refs_b, suggestions=suggestions,
        )


# ============ ⑥ 非主体件强度校核 ============

class AuxiliaryCheck(ComputeModule):
    id = "auxiliary_check"
    name = "非主体件强度校核"
    order = 6
    implemented = True

    @property
    def input_fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("overall.working_resistance", "工作阻力", "kN"),
            FieldSpec("overall.setting_load", "初撑力", "kN"),
            FieldSpec("overall.center_distance", "支架中心距", "mm"),
            FieldSpec("linkage.canopy_length", "顶梁长度", "mm"),
            FieldSpec("overall.support_strength", "要求支护强度", "MPa", required=False),
        ]

    def run(self, model: SupportDesignModel) -> ModuleResult:
        missing = self.validate_inputs(model)
        if missing:
            return ModuleResult(module=self.id, passed=None, results={"error": "missing_inputs"},
                                suggestions=[f"缺少必填参数: {', '.join(missing)}"])

        ov = model.overall
        refs, ratio_req, _ = _clause_ref("setting_load_ratio")
        ratio_req = ratio_req or 0.6
        ratio = ov.setting_load / ov.working_resistance

        q = ov.working_resistance * 1000 / (model.linkage.canopy_length * ov.center_distance)  # MPa
        refs_q, _, _ = _clause_ref("support_strength")

        margins = {"初撑力/工作阻力": round(ratio, 3), "实际支护强度(MPa)": round(q, 3)}
        checks_ok = [ratio >= ratio_req]
        suggestions = []
        if ratio < ratio_req:
            suggestions.append(f"初撑力占比 {ratio:.2f} < {ratio_req}, 建议提高泵站压力或增大缸径")
        if ov.support_strength:
            ok = q >= ov.support_strength
            checks_ok.append(ok)
            if not ok:
                suggestions.append(
                    f"实际支护强度 {q:.3f} MPa < 要求 {ov.support_strength} MPa, 需增大工作阻力或减小中心距")
        return ModuleResult(
            module=self.id, passed=all(checks_ok),
            results={"setting_ratio": round(ratio, 3), "support_strength_MPa": round(q, 3),
                     "note": "推移机构/侧护板等详细校核在详细设计阶段补充"},
            margins=margins, standard_refs=refs + refs_q, suggestions=suggestions,
        )


def register_all() -> None:
    for cls in (LinkageOptimization, LinkageSimulation, ForceAnalysis,
                StructureCheck, LegJackCheck, AuxiliaryCheck):
        registry.register(cls())
