"""REST API: 项目 / 方案 / 参数 / 快照 / 模块"""
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api import schemas
from app.db import get_db
from app.models.db_models import Design, Project, Snapshot
from app.models.knowledge_models import CaseRecord, Material, StandardClause
from app.models.support_model import CheckResult, LoadData, SupportDesignModel
from app.modules.base import registry

router = APIRouter(prefix="/api")


# ---------- 项目 ----------

@router.get("/projects", response_model=list[schemas.ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.scalars(select(Project).order_by(Project.updated_at.desc())).all()


@router.post("/projects", response_model=schemas.ProjectOut, status_code=201)
def create_project(body: schemas.ProjectCreate, db: Session = Depends(get_db)):
    project = Project(name=body.name, description=body.description)
    db.add(project)
    db.commit()
    return project


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "项目不存在")
    db.delete(project)
    db.commit()


# ---------- 方案 ----------

def _get_design(db: Session, design_id: int) -> Design:
    design = db.get(Design, design_id)
    if design is None:
        raise HTTPException(404, "方案不存在")
    return design


def _load_model(design: Design) -> SupportDesignModel:
    return SupportDesignModel.model_validate(design.model_data or {})


def _save_model(db: Session, design: Design, model: SupportDesignModel) -> None:
    design.model_data = model.model_dump(mode="json")
    db.commit()


@router.get("/projects/{project_id}/designs", response_model=list[schemas.DesignOut])
def list_designs(project_id: int, db: Session = Depends(get_db)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, "项目不存在")
    return db.scalars(select(Design).where(Design.project_id == project_id)).all()


@router.post("/projects/{project_id}/designs", response_model=schemas.DesignDetail, status_code=201)
def create_design(project_id: int, body: schemas.DesignCreate, db: Session = Depends(get_db)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, "项目不存在")
    model = SupportDesignModel()
    design = Design(project_id=project_id, name=body.name, model_data=model.model_dump(mode="json"))
    db.add(design)
    db.commit()
    return schemas.DesignDetail(**schemas.DesignOut.model_validate(design).model_dump(), model=model)


@router.get("/designs/{design_id}", response_model=schemas.DesignDetail)
def get_design(design_id: int, db: Session = Depends(get_db)):
    design = _get_design(db, design_id)
    return schemas.DesignDetail(
        **schemas.DesignOut.model_validate(design).model_dump(), model=_load_model(design)
    )


# ---------- 参数更新 (带脏标记传播) ----------

@router.patch("/designs/{design_id}/params", response_model=schemas.DesignDetail)
def update_params(design_id: int, body: schemas.ParamUpdate, db: Session = Depends(get_db)):
    design = _get_design(db, design_id)
    model = _load_model(design)

    if body.section not in ("meta", "overall", "linkage", "sections"):
        raise HTTPException(400, f"不支持的参数区块: {body.section}")

    block = getattr(model, body.section)
    try:
        updated = block.model_copy(update=body.values)
        # 触发校验
        updated = type(block).model_validate(updated.model_dump())
    except Exception as e:
        raise HTTPException(422, f"参数校验失败: {e}")

    setattr(model, body.section, updated)
    model.mark_upstream_changed(body.section)
    _save_model(db, design, model)
    return schemas.DesignDetail(
        **schemas.DesignOut.model_validate(design).model_dump(), model=model
    )


@router.get("/designs/{design_id}/completeness")
def get_completeness(design_id: int, db: Session = Depends(get_db)):
    design = _get_design(db, design_id)
    return _load_model(design).completeness()


# ---------- 快照 ----------

def _create_snapshot(db: Session, design: Design, label: str, trigger: str) -> Snapshot:
    next_seq = (db.scalar(
        select(func.max(Snapshot.seq)).where(Snapshot.design_id == design.id)
    ) or 0) + 1
    snap = Snapshot(
        design_id=design.id, seq=next_seq, label=label,
        trigger=trigger, model_data=design.model_data,
    )
    db.add(snap)
    db.commit()
    return snap


@router.get("/designs/{design_id}/snapshots", response_model=list[schemas.SnapshotOut])
def list_snapshots(design_id: int, db: Session = Depends(get_db)):
    _get_design(db, design_id)
    return db.scalars(
        select(Snapshot).where(Snapshot.design_id == design_id).order_by(Snapshot.seq.desc())
    ).all()


@router.post("/designs/{design_id}/snapshots", response_model=schemas.SnapshotOut, status_code=201)
def create_snapshot(design_id: int, label: str = "", db: Session = Depends(get_db)):
    design = _get_design(db, design_id)
    return _create_snapshot(db, design, label, "manual")


@router.get("/designs/{design_id}/snapshots/{snapshot_id}", response_model=schemas.DesignDetail)
def get_snapshot(design_id: int, snapshot_id: int, db: Session = Depends(get_db)):
    design = _get_design(db, design_id)
    snap = db.get(Snapshot, snapshot_id)
    if snap is None or snap.design_id != design_id:
        raise HTTPException(404, "快照不存在")
    return schemas.DesignDetail(
        **schemas.DesignOut.model_validate(design).model_dump(),
        model=SupportDesignModel.model_validate(snap.model_data),
    )


@router.post("/designs/{design_id}/snapshots/{snapshot_id}/restore", response_model=schemas.DesignDetail)
def restore_snapshot(design_id: int, snapshot_id: int, db: Session = Depends(get_db)):
    design = _get_design(db, design_id)
    snap = db.get(Snapshot, snapshot_id)
    if snap is None or snap.design_id != design_id:
        raise HTTPException(404, "快照不存在")
    _create_snapshot(db, design, f"回滚到快照#{snap.seq}前的自动备份", "pre_restore")
    design.model_data = snap.model_data
    db.commit()
    return schemas.DesignDetail(
        **schemas.DesignOut.model_validate(design).model_dump(), model=_load_model(design)
    )


# ---------- 报告 ----------

@router.get("/designs/{design_id}/report")
def get_report(design_id: int, format: str = "markdown", db: Session = Depends(get_db)):
    from fastapi.responses import HTMLResponse, PlainTextResponse

    from app.report import generate_html, generate_markdown

    design = _get_design(db, design_id)
    model = _load_model(design)
    if format == "html":
        return HTMLResponse(generate_html(design.name, model))
    return PlainTextResponse(generate_markdown(design.name, model),
                             media_type="text/markdown; charset=utf-8")


# ---------- 知识层 ----------

@router.get("/knowledge/standards")
def list_standards(module: str = "", q: str = "", db: Session = Depends(get_db)):
    stmt = select(StandardClause)
    if module:
        stmt = stmt.where(StandardClause.module_id == module)
    if q:
        stmt = stmt.where(StandardClause.content.contains(q) | StandardClause.title.contains(q))
    return [
        {"standard_code": s.standard_code, "clause_no": s.clause_no, "title": s.title,
         "content": s.content, "param_key": s.param_key, "limit_type": s.limit_type,
         "limit_min": s.limit_min, "limit_max": s.limit_max, "unit": s.unit,
         "module_id": s.module_id}
        for s in db.scalars(stmt).all()
    ]


@router.get("/knowledge/materials")
def list_materials(db: Session = Depends(get_db)):
    return [
        {"grade": m.grade, "yield_strength": m.yield_strength,
         "tensile_strength": m.tensile_strength, "elastic_modulus": m.elastic_modulus,
         "description": m.description}
        for m in db.scalars(select(Material)).all()
    ]


@router.get("/knowledge/cases")
def list_cases(support_type: str = "", db: Session = Depends(get_db)):
    stmt = select(CaseRecord)
    if support_type:
        stmt = stmt.where(CaseRecord.support_type == support_type)
    return [
        {"name": c.name, "support_type": c.support_type, "params": c.params,
         "results": c.results, "notes": c.notes}
        for c in db.scalars(stmt).all()
    ]


def apply_module_result(model: SupportDesignModel, module_id: str, result) -> None:
    """模块结果写回数据模型 — 传统模式与 Agent 模式共用 (确定性代码, LLM 不经手数值)"""
    # 1) 参数区块写回 (如连杆优化输出几何参数), 触发脏标记传播
    for section, values in result.model_updates.items():
        if section == "loads":
            continue
        block = getattr(model, section, None)
        if block is not None:
            setattr(model, section, type(block).model_validate({**block.model_dump(), **values}))
            model.mark_upstream_changed(section)
    # 2) 载荷写回
    if "loads" in result.model_updates:
        model.set_loads(LoadData.model_validate(result.model_updates["loads"]))
    # 3) 校核结论写回
    if result.passed is not None or result.margins or result.standard_refs:
        model.set_check(CheckResult(
            module=module_id, passed=result.passed,
            margins=result.margins, standard_refs=result.standard_refs,
            suggestions=result.suggestions, detail=result.results,
        ))


# ---------- 模块 ----------

@router.get("/modules", response_model=list[schemas.ModuleInfo])
def list_modules():
    return [
        schemas.ModuleInfo(
            id=m.id, name=m.name, order=m.order, implemented=m.implemented,
            input_fields=[asdict(f) for f in m.input_fields],
        )
        for m in registry.list_ordered()
    ]


@router.get("/designs/{design_id}/modules", response_model=list[schemas.ModuleInfo])
def list_modules_for_design(design_id: int, db: Session = Depends(get_db)):
    """模块列表 + 该方案下的输入完整性与脏状态 (模块树渲染用)"""
    design = _get_design(db, design_id)
    model = _load_model(design)
    out = []
    for m in registry.list_ordered():
        if m.id == "force_analysis":
            dirty = model.loads.dirty
        else:
            check = model.checks.get(m.id)
            dirty = check.dirty if check else None
        out.append(schemas.ModuleInfo(
            id=m.id, name=m.name, order=m.order, implemented=m.implemented,
            input_fields=[asdict(f) for f in m.input_fields],
            missing_inputs=m.validate_inputs(model),
            dirty=dirty,
        ))
    return out


@router.post("/designs/{design_id}/modules/{module_id}/run", response_model=schemas.ModuleRunResult)
def run_module(design_id: int, module_id: str, db: Session = Depends(get_db)):
    design = _get_design(db, design_id)
    try:
        module = registry.get(module_id)
    except KeyError:
        raise HTTPException(404, f"未知模块: {module_id}")

    model = _load_model(design)
    snap = _create_snapshot(db, design, f"运行[{module.name}]前自动快照", "pre_compute")

    result = module.run(model)

    # 结果写回数据模型 (载荷传递由框架代码完成, 不经 LLM)
    apply_module_result(model, module_id, result)
    _save_model(db, design, model)

    return schemas.ModuleRunResult(
        module=result.module, passed=result.passed, results=result.results,
        margins=result.margins, suggestions=result.suggestions,
        standard_refs=result.standard_refs, snapshot_id=snap.id,
    )
