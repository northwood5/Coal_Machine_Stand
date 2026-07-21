"""M2 计算内核 + M3 知识层 验收测试: 全主线流程 ①→⑥"""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test_m2.db")

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def design_id(client):
    p = client.post("/api/projects", json={"name": "M2验收"}).json()
    d = client.post(f"/api/projects/{p['id']}/designs", json={"name": "ZY12000/24/50"}).json()
    did = d["id"]
    # 总体参数 (典型两柱掩护式大采高支架)
    client.patch(f"/api/designs/{did}/params", json={"section": "overall", "values": {
        "height_min": 2400, "height_max": 5000, "working_resistance": 12000,
        "setting_load": 9600, "center_distance": 1750, "support_strength": 1.3,
        "pump_pressure": 31.5,
    }})
    client.patch(f"/api/designs/{did}/params", json={"section": "linkage", "values": {
        "lemniscate_width_limit": 70, "canopy_length": 4500, "leg_hinge_x": 2000,
    }})
    client.patch(f"/api/designs/{did}/params", json={"section": "sections", "values": {
        "canopy_web_thickness": 40, "canopy_flange_thickness": 50,
        "canopy_height": 700, "canopy_section_width": 500,
        "link_section_width": 300, "link_section_height": 400,
        "leg_cylinder_bore": 400, "leg_rod_diameter": 380, "leg_wall_thickness": 60,
        "material_grade": "Q690", "leg_material_grade": "27SiMn",
    }})
    return did


def _run(client, did, module_id):
    resp = client.post(f"/api/designs/{did}/modules/{module_id}/run")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_01_linkage_optimization(client, design_id):
    body = _run(client, design_id, "linkage_optimization")
    assert body["passed"] is True, body
    assert body["results"]["lemniscate_width"] <= 70
    assert body["standard_refs"]        # 对标 GB 25974
    # 几何已写回数据模型
    model = client.get(f"/api/designs/{design_id}").json()["model"]
    assert model["linkage"]["rear_link_length"] is not None


def test_02_linkage_simulation(client, design_id):
    body = _run(client, design_id, "linkage_simulation")
    assert body["passed"] is True, body
    assert len(body["results"]["trajectory"]) > 20   # 轨迹点供前端可视化


def test_03_force_analysis(client, design_id):
    body = _run(client, design_id, "force_analysis")
    assert "error" not in body["results"], body
    assert len(body["results"]["cases"]) == 4
    assert body["results"]["leg_force_max"] > 0
    # 载荷已写入且不脏
    model = client.get(f"/api/designs/{design_id}").json()["model"]
    assert model["loads"]["dirty"] is False
    assert len(model["loads"]["cases"]) == 4


def test_04_structure_check(client, design_id):
    body = _run(client, design_id, "structure_check")
    assert body["passed"] is True, body
    assert all(n >= 1.5 for n in body["margins"].values()), body["margins"]


def test_05_leg_jack_check(client, design_id):
    body = _run(client, design_id, "leg_jack_check")
    assert body["passed"] is True, body
    # 工作压强应在合理范围 (30~60 MPa)
    assert 20 < body["results"]["work_pressure_MPa"] < 80


def test_06_auxiliary_check(client, design_id):
    body = _run(client, design_id, "auxiliary_check")
    assert body["passed"] is True, body
    assert body["results"]["setting_ratio"] == 0.8


def test_07_dirty_blocks_stale_check(client, design_id):
    """改截面参数 → 校核标脏; 校核模块拒绝使用过期载荷之外的场景 (载荷未脏仍可跑)"""
    client.patch(f"/api/designs/{design_id}/params", json={
        "section": "sections", "values": {"canopy_web_thickness": 30}})
    model = client.get(f"/api/designs/{design_id}").json()["model"]
    assert model["loads"]["dirty"] is True
    # 载荷已脏 → 结构校核应拒绝
    body = _run(client, design_id, "structure_check")
    assert body["results"].get("error") == "loads_dirty"
    # 重跑受力分析后恢复
    _run(client, design_id, "force_analysis")
    body = _run(client, design_id, "structure_check")
    assert "error" not in body["results"]


def test_knowledge_standards(client):
    stds = client.get("/api/knowledge/standards").json()
    assert len(stds) >= 7
    lem = client.get("/api/knowledge/standards", params={"module": "linkage_optimization"}).json()
    assert any(s["param_key"] == "lemniscate_width" for s in lem)


def test_knowledge_materials_and_cases(client):
    mats = client.get("/api/knowledge/materials").json()
    assert any(m["grade"] == "Q690" for m in mats)
    cases = client.get("/api/knowledge/cases", params={"support_type": "shield_2leg"}).json()
    assert len(cases) >= 2
