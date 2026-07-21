"""设计计算报告生成 (Markdown / 独立 HTML)"""
from datetime import datetime

from app.models.support_model import SupportDesignModel
from app.modules.base import registry

_SECTION_LABELS = {
    "overall": "总体参数", "linkage": "四连杆与布置参数", "sections": "截面与材料参数",
}

_FIELD_LABELS = {
    "height_min": "最低支撑高度(mm)", "height_max": "最高支撑高度(mm)",
    "working_resistance": "工作阻力(kN)", "setting_load": "初撑力(kN)",
    "center_distance": "中心距(mm)", "support_strength": "要求支护强度(MPa)",
    "pump_pressure": "泵站压力(MPa)", "width_min": "最小宽度(mm)", "width_max": "最大宽度(mm)",
    "floor_pressure_max": "对底板最大比压(MPa)",
    "rear_link_length": "后连杆长度(mm)", "front_link_length": "前连杆长度(mm)",
    "shield_beam_length": "掩护梁长度E-C(mm)", "shield_top_to_front_hinge": "E-前连杆上铰点(mm)",
    "rear_link_lower_hinge": "后连杆下铰点(mm)", "front_link_lower_hinge": "前连杆下铰点(mm)",
    "front_link_upper_hinge": "前连杆上铰点(mm)", "rear_link_upper_hinge": "后连杆上铰点(mm)",
    "lemniscate_width_limit": "双纽线宽度限值(mm)", "canopy_length": "顶梁长度(mm)",
    "leg_hinge_x": "柱窝距E水平距离(mm)", "leg_count": "立柱数量",
    "canopy_web_thickness": "顶梁腹板厚(mm)", "canopy_flange_thickness": "顶梁盖板厚(mm)",
    "canopy_height": "顶梁截面高(mm)", "canopy_section_width": "箱形截面宽(mm)",
    "shield_web_thickness": "掩护梁腹板厚(mm)", "shield_flange_thickness": "掩护梁盖板厚(mm)",
    "base_web_thickness": "底座腹板厚(mm)", "link_section_width": "连杆截面宽(mm)",
    "link_section_height": "连杆截面高(mm)", "leg_cylinder_bore": "立柱缸径(mm)",
    "leg_rod_diameter": "活塞杆径(mm)", "leg_wall_thickness": "缸体壁厚(mm)",
    "material_grade": "主体材料", "leg_material_grade": "立柱材料",
}


def generate_markdown(design_name: str, model: SupportDesignModel) -> str:
    lines = [
        f"# 液压支架总体设计计算报告",
        "",
        f"- **方案**: {design_name}",
        f"- **型号**: {model.meta.name or '(未命名)'}    **架型**: {model.meta.support_type.value}",
        f"- **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    # 参数表
    for section in ("overall", "linkage", "sections"):
        block = getattr(model, section)
        rows = [(k, v) for k, v in block.model_dump().items() if v is not None]
        if not rows:
            continue
        lines += [f"## {_SECTION_LABELS[section]}", "", "| 参数 | 数值 |", "|---|---|"]
        lines += [f"| {_FIELD_LABELS.get(k, k)} | {v} |" for k, v in rows]
        lines.append("")

    # 载荷
    if model.loads.cases and not model.loads.dirty:
        lines += ["## 受力分析结果",
                  f"(分析高度 {model.loads.height_analyzed:.0f} mm)", "",
                  "| 工况 | 载荷(kN) | 立柱力(kN) | 前连杆力(kN) | 后连杆力(kN) | 顶梁弯矩(kN·m) |",
                  "|---|---|---|---|---|---|"]
        for c in model.loads.cases:
            lines.append(
                f"| {c.description} | {c.extra.get('applied_load_kN','—')} | {c.leg_force} "
                f"| {c.front_link_force} | {c.rear_link_force} | {c.canopy_moment_max} |")
        lines.append("")

    # 校核结论
    lines += ["## 校核结论", ""]
    module_names = {m.id: m.name for m in registry.list_ordered()}
    all_pass = True
    any_check = False
    for mid, name in module_names.items():
        check = model.checks.get(mid)
        if check is None or check.passed is None:
            continue
        any_check = True
        icon = "✅ 通过" if check.passed else "❌ 不通过"
        stale = "(已过期, 需重算)" if check.dirty else ""
        all_pass = all_pass and bool(check.passed) and not check.dirty
        lines.append(f"### {name}: {icon} {stale}")
        if check.margins:
            lines += ["", "| 校核项 | 安全系数/数值 |", "|---|---|"]
            lines += [f"| {k} | {v} |" for k, v in check.margins.items()]
        if check.standard_refs:
            lines.append(f"\n依据: {'; '.join(check.standard_refs)}")
        if check.suggestions:
            lines += [""] + [f"> 建议: {s}" for s in check.suggestions]
        lines.append("")

    if any_check:
        lines += ["## 总体评估", "",
                  "各项校核全部通过, 方案可进入详细设计阶段。" if all_pass
                  else "存在未通过或已过期的校核项, 需按上述建议调整后复核。", ""]
    lines += ["---",
              "*本报告由液压支架总体设计 Agent 自动生成, 采用总体设计阶段简化力学模型, "
              "详细设计阶段应以有限元复核; 标准条款以正式出版文本为准。*"]
    return "\n".join(lines)


def generate_html(design_name: str, model: SupportDesignModel) -> str:
    """极简 Markdown→HTML (仅支持本报告用到的语法), 生成可打印的独立页面"""
    md = generate_markdown(design_name, model)
    body: list[str] = []
    in_table = False
    for line in md.split("\n"):
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= {"-"} for c in cells):
                continue
            tag = "th" if not in_table else "td"
            if not in_table:
                body.append("<table>")
                in_table = True
            body.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>")
            continue
        if in_table:
            body.append("</table>")
            in_table = False
        if line.startswith("### "):
            body.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            body.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            body.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("> "):
            body.append(f"<blockquote>{line[2:]}</blockquote>")
        elif line.startswith("- "):
            body.append(f"<p class='meta'>{line[2:]}</p>")
        elif line == "---":
            body.append("<hr/>")
        elif line.strip():
            body.append(f"<p>{line}</p>")
    if in_table:
        body.append("</table>")
    content = "\n".join(body).replace("**", "")
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>设计计算报告 - {design_name}</title>
<style>
body{{font-family:'Microsoft YaHei',sans-serif;max-width:860px;margin:24px auto;color:#2d3748;padding:0 16px}}
h1{{border-bottom:2px solid #1f3a5f;padding-bottom:8px}}
h2{{color:#1f3a5f;margin-top:28px}}
table{{border-collapse:collapse;width:100%;margin:8px 0;font-size:14px}}
td,th{{border:1px solid #cbd5e0;padding:5px 10px;text-align:left}}
th{{background:#eef2f7}}
blockquote{{border-left:3px solid #e67e22;margin:6px 0;padding:4px 12px;color:#8a5a00;background:#fdf6ec}}
@media print{{body{{margin:0}}}}
</style></head><body>{content}</body></html>"""
