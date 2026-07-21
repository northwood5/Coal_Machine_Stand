"""知识层种子数据。

注意: 条款限值为工程常用示例值, 供系统联调与演示;
正式使用前须由工程师按现行标准原文逐条核对录入。
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.knowledge_models import CaseRecord, Material, StandardClause

STANDARD_SEED = [
    # (standard, clause, title, content, param_key, type, min, max, unit, module)
    ("GB 25974.1-2010", "4.5.1", "结构件强度安全系数",
     "支架主要结构件按额定工作阻力计算的强度安全系数不应小于1.5。",
     "structure_safety_factor", "min", 1.5, None, "", "structure_check"),
    ("GB 25974.1-2010", "4.4.2", "双纽线宽度",
     "支架在最低至最高工作高度范围内, 顶梁前端运动轨迹(双纽线)宽度不宜大于70mm。",
     "lemniscate_width", "max", None, 70.0, "mm", "linkage_optimization"),
    ("GB 25974.1-2010", "4.6.3", "初撑力与工作阻力比",
     "支架初撑力不应小于额定工作阻力的60%。",
     "setting_load_ratio", "min", 0.6, None, "", "auxiliary_check"),
    ("GB 25974.2-2010", "4.3.1", "立柱缸体强度安全系数",
     "缸体按试验压力计算的强度安全系数不应小于1.5。",
     "leg_cylinder_safety_factor", "min", 1.5, None, "", "leg_jack_check"),
    ("GB 25974.2-2010", "4.3.5", "立柱稳定性安全系数",
     "立柱在最大工作长度下的压杆稳定性安全系数不应小于2.0。",
     "leg_buckling_safety_factor", "min", 2.0, None, "", "leg_jack_check"),
    ("MT/T 587-2011", "5.2", "连杆销轴孔挤压强度",
     "连杆销轴孔挤压应力安全系数不应小于1.2。",
     "link_bearing_safety_factor", "min", 1.2, None, "", "structure_check"),
    ("GB 25974.1-2010", "4.2.4", "支护强度",
     "支架支护强度应满足工作面顶板控制设计要求。",
     "support_strength", "min", None, None, "MPa", "auxiliary_check"),
]

MATERIAL_SEED = [
    # (grade, yield, tensile, description)
    ("Q345", 345.0, 490.0, "普通低合金结构钢, 用于次要结构件"),
    ("Q550", 550.0, 670.0, "高强钢, 用于顶梁/底座主筋板"),
    ("Q690", 690.0, 770.0, "高强钢, 主流支架主体结构材料"),
    ("Q890", 890.0, 940.0, "超高强钢, 大采高重型支架"),
    ("27SiMn", 835.0, 980.0, "立柱缸体常用调质钢"),
    ("30CrMnSi", 885.0, 1080.0, "活塞杆用调质钢"),
]

CASE_SEED = [
    ("ZY12000/25/50D", "shield_2leg",
     {"height_min": 2500, "height_max": 5000, "working_resistance": 12000,
      "center_distance": 1750, "leg_cylinder_bore": 400},
     {"lemniscate_width": 52.3, "type_test": "通过"},
     "两柱掩护式, 大采高工作面, 型式检验通过"),
    ("ZY21000/38/82D", "shield_2leg",
     {"height_min": 3800, "height_max": 8200, "working_resistance": 21000,
      "center_distance": 2400, "leg_cylinder_bore": 630},
     {"lemniscate_width": 64.1, "type_test": "通过"},
     "8m 大采高重型支架案例"),
    ("ZF6800/18/35", "shield_4leg",
     {"height_min": 1800, "height_max": 3500, "working_resistance": 6800,
      "center_distance": 1500, "leg_cylinder_bore": 320},
     {"lemniscate_width": 48.0, "type_test": "通过"},
     "四柱放顶煤支架案例"),
]


def seed_knowledge(db: Session) -> None:
    """幂等种子: 已有数据则跳过"""
    if db.scalar(select(StandardClause).limit(1)) is None:
        for s in STANDARD_SEED:
            db.add(StandardClause(
                standard_code=s[0], clause_no=s[1], title=s[2], content=s[3],
                param_key=s[4], limit_type=s[5], limit_min=s[6], limit_max=s[7],
                unit=s[8], module_id=s[9],
            ))
    if db.scalar(select(Material).limit(1)) is None:
        for m in MATERIAL_SEED:
            db.add(Material(grade=m[0], yield_strength=m[1], tensile_strength=m[2], description=m[3]))
    if db.scalar(select(CaseRecord).limit(1)) is None:
        for c in CASE_SEED:
            db.add(CaseRecord(name=c[0], support_type=c[1], params=c[2], results=c[3], notes=c[4]))
    db.commit()


def get_material(db: Session, grade: str) -> Material | None:
    return db.scalar(select(Material).where(Material.grade == grade))


def get_clause(db: Session, param_key: str) -> StandardClause | None:
    return db.scalar(select(StandardClause).where(StandardClause.param_key == param_key))
