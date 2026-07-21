"""M1 骨架验收测试: 数据模型 / 项目库 / API / 模块协议"""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# 每次测试用独立临时库
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"

from app.main import app  # noqa: E402
from app.models.support_model import SupportDesignModel  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def design_id(client):
    project = client.post("/api/projects", json={"name": "测试项目", "description": "M1 验收"}).json()
    design = client.post(f"/api/projects/{project['id']}/designs", json={"name": "方案A"}).json()
    return design["id"]


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_project_crud(client):
    resp = client.post("/api/projects", json={"name": "P1"})
    assert resp.status_code == 201
    pid = resp.json()["id"]
    assert any(p["id"] == pid for p in client.get("/api/projects").json())
    assert client.delete(f"/api/projects/{pid}").status_code == 204


def test_six_modules_registered(client):
    modules = client.get("/api/modules").json()
    assert [m["id"] for m in modules] == [
        "linkage_optimization", "linkage_simulation", "force_analysis",
        "structure_check", "leg_jack_check", "auxiliary_check",
    ]
    assert all(m["implemented"] for m in modules)  # M2 起全部为真实实现


def test_param_update_and_validation(client, design_id):
    resp = client.patch(f"/api/designs/{design_id}/params", json={
        "section": "overall",
        "values": {"working_resistance": 12000, "height_min": 2400, "height_max": 5000},
    })
    assert resp.status_code == 200
    model = resp.json()["model"]
    assert model["overall"]["working_resistance"] == 12000

    # 非法区块
    assert client.patch(f"/api/designs/{design_id}/params", json={
        "section": "bogus", "values": {}
    }).status_code == 400


def test_dirty_propagation(client, design_id):
    """上游参数变更 → loads/checks 标脏"""
    modules = client.get(f"/api/designs/{design_id}/modules").json()
    force = next(m for m in modules if m["id"] == "force_analysis")
    assert force["dirty"] is True  # 初始即脏 (从未计算)

    # 数据模型层面验证传播逻辑
    m = SupportDesignModel()
    from app.models.support_model import CheckResult, LoadData
    m.set_loads(LoadData(cases=[]))
    m.set_check(CheckResult(module="structure_check", passed=True))
    assert m.loads.dirty is False and m.checks["structure_check"].dirty is False

    m.mark_upstream_changed("sections")
    assert m.loads.dirty is True and m.checks["structure_check"].dirty is True


def test_snapshot_lifecycle(client, design_id):
    # 手动快照
    snap = client.post(f"/api/designs/{design_id}/snapshots", params={"label": "基线"}).json()
    assert snap["seq"] >= 1

    # 改参数后回滚
    client.patch(f"/api/designs/{design_id}/params", json={
        "section": "overall", "values": {"working_resistance": 99999}
    })
    restored = client.post(f"/api/designs/{design_id}/snapshots/{snap['id']}/restore").json()
    assert restored["model"]["overall"]["working_resistance"] == 12000


def test_module_run_reports_missing_inputs(client, design_id):
    # 运动仿真需要连杆几何, 新方案未填 → 报缺参
    resp = client.post(f"/api/designs/{design_id}/modules/linkage_simulation/run")
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"]["error"] == "missing_inputs"
    assert body["snapshot_id"] > 0


def test_completeness(client, design_id):
    missing = client.get(f"/api/designs/{design_id}/completeness").json()
    assert "linkage" in missing  # 连杆参数还有空缺
