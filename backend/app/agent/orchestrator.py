"""智能体编排层。

职责: 意图理解交给 LLM; 本层提供工具集、执行工具调用、
管理载荷传递 (确定性代码)、限制循环次数、持久化对话。
LLM 只决定"下一步做什么", 不经手数值计算。
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Callable, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import apply_module_result
from app.llm.base import LLMAdapter, ToolDef
from app.models.db_models import Design
from app.models.knowledge_models import CaseRecord, Material, StandardClause
from app.models.support_model import SupportDesignModel
from app.modules.base import registry

MAX_ITERATIONS = 20          # 单轮对话最大工具调用循环数

SYSTEM_PROMPT = """你是液压支架总体设计智能体, 帮助工程师完成采煤工作面液压支架的方案设计。

## 设计主线流程
①连杆优化设计 → ②连杆运动仿真 → ③支架受力分析 → ④结构件强度校核 → ⑤立柱千斤强度校核 → ⑥非主体件强度校核 → 合理性评估

## 工作准则
1. 先用 get_design_state 了解当前设计状态, 判断参数缺口; 缺少必要参数时向用户询问, 不要凭空编造。
2. 按主线顺序推进; 上游结果标脏(dirty)时须先重跑上游模块。
3. 校核不通过时: 阅读模块返回的 suggestions, 用 update_params 调整参数后重跑, 同一模块最多重试 3 次; 仍不通过则向用户说明原因并请求决策。
4. 参数取值可参考 query_cases 中的相似案例与 query_materials 的材料数据。
5. 每完成一个模块, 用一两句话向用户汇报结论 (通过/不通过、关键数值)。
6. 最终完成后给出整体评估: 各项校核结论、薄弱环节、建议。
7. 单位: 长度 mm, 力 kN, 压强/应力 MPa。回答使用中文。"""


def _get_model(db: Session, design_id: int) -> tuple[Design, SupportDesignModel]:
    design = db.get(Design, design_id)
    if design is None:
        raise ValueError(f"方案不存在: {design_id}")
    return design, SupportDesignModel.model_validate(design.model_data or {})


def build_tools() -> list[ToolDef]:
    return [
        ToolDef("get_design_state", "获取当前设计的全部参数、载荷与校核状态, 以及各模块的输入完整性和脏标记。开始任何工作前先调用。",
                {"type": "object", "properties": {}, "required": []}),
        ToolDef("update_params", "更新设计参数。section 取 meta|overall|linkage|sections, values 为字段字典。上游参数变更会自动将下游载荷/校核标脏。",
                {"type": "object", "properties": {
                    "section": {"type": "string", "enum": ["meta", "overall", "linkage", "sections"]},
                    "values": {"type": "object"}},
                 "required": ["section", "values"]}),
        ToolDef("run_module", "运行计算模块。module_id 取: linkage_optimization | linkage_simulation | force_analysis | structure_check | leg_jack_check | auxiliary_check。结果自动写回数据模型(载荷传递由框架完成)。",
                {"type": "object", "properties": {
                    "module_id": {"type": "string"}},
                 "required": ["module_id"]}),
        ToolDef("query_standards", "查询标准规范条款 (GB 25974 / MT/T 587)。可按模块过滤。",
                {"type": "object", "properties": {
                    "module_id": {"type": "string", "description": "可选, 按模块过滤"}},
                 "required": []}),
        ToolDef("query_materials", "查询材料库 (牌号/屈服强度/抗拉强度)。",
                {"type": "object", "properties": {}, "required": []}),
        ToolDef("query_cases", "查询历史架型案例库, 可按架型过滤 (shield_2leg|shield_4leg|chock)。用于参数初值参考。",
                {"type": "object", "properties": {
                    "support_type": {"type": "string"}},
                 "required": []}),
    ]


def execute_tool(db: Session, design_id: int, name: str, args: dict) -> str:
    """执行工具, 返回 JSON 字符串结果"""
    try:
        result = _execute(db, design_id, name, args)
    except Exception as e:
        result = {"error": str(e)}
    return json.dumps(result, ensure_ascii=False, default=str)


def _execute(db: Session, design_id: int, name: str, args: dict):
    if name == "get_design_state":
        design, model = _get_model(db, design_id)
        modules_state = []
        for m in registry.list_ordered():
            check = model.checks.get(m.id)
            modules_state.append({
                "id": m.id, "name": m.name,
                "missing_inputs": m.validate_inputs(model),
                "dirty": (model.loads.dirty if m.id == "force_analysis"
                          else (check.dirty if check else None)),
                "passed": check.passed if check else None,
            })
        return {"design_name": design.name, "model": model.model_dump(mode="json"),
                "modules": modules_state}

    if name == "update_params":
        design, model = _get_model(db, design_id)
        section, values = args["section"], args["values"]
        block = getattr(model, section, None)
        if block is None:
            return {"error": f"未知区块 {section}"}
        updated = type(block).model_validate({**block.model_dump(), **values})
        setattr(model, section, updated)
        model.mark_upstream_changed(section)
        design.model_data = model.model_dump(mode="json")
        db.commit()
        return {"ok": True, "section": section, "updated_fields": list(values.keys())}

    if name == "run_module":
        design, model = _get_model(db, design_id)
        module = registry.get(args["module_id"])
        result = module.run(model)
        apply_module_result(model, module.id, result)
        design.model_data = model.model_dump(mode="json")
        db.commit()
        return {"module": module.id, "passed": result.passed, "results": result.results,
                "margins": result.margins, "suggestions": result.suggestions,
                "standard_refs": result.standard_refs}

    if name == "query_standards":
        stmt = select(StandardClause)
        if args.get("module_id"):
            stmt = stmt.where(StandardClause.module_id == args["module_id"])
        return [{"ref": s.ref(), "content": s.content, "param_key": s.param_key,
                 "limit_min": s.limit_min, "limit_max": s.limit_max} for s in db.scalars(stmt)]

    if name == "query_materials":
        return [{"grade": m.grade, "yield_strength": m.yield_strength,
                 "tensile_strength": m.tensile_strength} for m in db.scalars(select(Material))]

    if name == "query_cases":
        stmt = select(CaseRecord)
        if args.get("support_type"):
            stmt = stmt.where(CaseRecord.support_type == args["support_type"])
        return [{"name": c.name, "support_type": c.support_type, "params": c.params,
                 "results": c.results, "notes": c.notes} for c in db.scalars(stmt)]

    return {"error": f"未知工具 {name}"}


def run_agent_turn(
    db: Session, adapter: LLMAdapter, design_id: int,
    history: list[dict], user_message: str,
) -> Iterator[dict]:
    """执行一轮对话 (含多轮工具调用循环)。

    产出事件流: {"type": "text"|"tool_call"|"tool_result"|"done"|"error", ...}
    history 会被就地追加 (调用方负责持久化)。
    """
    tools = build_tools()
    history.append({"role": "user", "content": user_message})

    for _ in range(MAX_ITERATIONS):
        try:
            reply = adapter.chat(SYSTEM_PROMPT, history, tools)
        except Exception as e:
            yield {"type": "error", "message": f"LLM 调用失败: {e}"}
            return

        assistant_msg: dict = {"role": "assistant", "content": reply.text,
                               "tool_calls": [asdict(tc) for tc in reply.tool_calls]}
        history.append(assistant_msg)
        if reply.text:
            yield {"type": "text", "content": reply.text}

        if not reply.tool_calls:
            yield {"type": "done"}
            return

        for tc in reply.tool_calls:
            yield {"type": "tool_call", "name": tc.name, "arguments": tc.arguments}
            result = execute_tool(db, design_id, tc.name, tc.arguments)
            history.append({"role": "tool", "tool_call_id": tc.id, "content": result})
            # 截断过大的结果用于前端展示 (完整结果已入 history)
            display = result if len(result) < 2000 else result[:2000] + "…(截断)"
            yield {"type": "tool_result", "name": tc.name, "result": display}

    yield {"type": "error", "message": f"超过最大循环次数 {MAX_ITERATIONS}, 已停止; 请检查任务或分步执行"}
