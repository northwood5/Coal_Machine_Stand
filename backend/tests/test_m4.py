"""M4 智能体层验收测试: 编排循环 (FakeAdapter 驱动) / 设置API / 对话历史"""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test_m4.db")

from app.agent.orchestrator import run_agent_turn  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.llm.base import LLMAdapter, LLMReply, ToolCallReq  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def design_id(client):
    p = client.post("/api/projects", json={"name": "M4验收"}).json()
    d = client.post(f"/api/projects/{p['id']}/designs", json={"name": "Agent方案"}).json()
    return d["id"]


class ScriptedAdapter(LLMAdapter):
    """按脚本回放的假 LLM: 查状态 → 填参数 → 跑模块 → 汇报"""

    def __init__(self):
        self.script = [
            LLMReply(text="我先查看当前设计状态。",
                     tool_calls=[ToolCallReq("t1", "get_design_state", {})]),
            LLMReply(text="参数缺失, 我先补齐总体参数。",
                     tool_calls=[ToolCallReq("t2", "update_params", {
                         "section": "overall",
                         "values": {"height_min": 2400, "height_max": 5000,
                                    "working_resistance": 12000}})]),
            LLMReply(text="运行连杆优化。",
                     tool_calls=[ToolCallReq("t3", "run_module",
                                             {"module_id": "linkage_optimization"})]),
            LLMReply(text="连杆优化完成, 双纽线宽度满足要求。设计推进中。"),
        ]
        self.calls = 0

    def chat(self, system, messages, tools):
        assert "液压支架" in system            # 系统提示已注入
        assert len(tools) == 6                 # 六个工具
        reply = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        return reply


def test_orchestrator_loop(client, design_id):
    adapter = ScriptedAdapter()
    history: list[dict] = []
    with SessionLocal() as db:
        events = list(run_agent_turn(db, adapter, design_id, history, "帮我设计一个大采高支架"))

    types = [e["type"] for e in events]
    assert types.count("tool_call") == 3
    assert types.count("tool_result") == 3
    assert types[-1] == "done"
    # 工具真实生效: 参数已写入且模块已运行
    model = client.get(f"/api/designs/{design_id}").json()["model"]
    assert model["overall"]["working_resistance"] == 12000
    assert model["linkage"]["rear_link_length"] is not None
    assert "linkage_optimization" in model["checks"]
    # history 结构完整 (user/assistant/tool 交替)
    roles = [m["role"] for m in history]
    assert roles[0] == "user" and "tool" in roles


def test_llm_settings_api(client):
    # 未配置时对话应报 409
    resp = client.post("/api/designs/1/agent/chat", json={"message": "hi"})
    assert resp.status_code == 409

    # 配置
    resp = client.put("/api/settings/llm", json={
        "provider": "openai_compat", "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1", "api_key": "sk-test-1234"})
    body = resp.json()
    assert body["configured"] is True
    assert body["api_key_masked"] == "…1234"       # key 不明文返回

    # 更新时空 key 保留原值
    client.put("/api/settings/llm", json={
        "provider": "anthropic", "model": "claude-opus-4-8", "base_url": "", "api_key": ""})
    body = client.get("/api/settings/llm").json()
    assert body["provider"] == "anthropic" and body["configured"] is True

    # 非法 provider
    assert client.put("/api/settings/llm", json={
        "provider": "bogus", "api_key": "x"}).status_code == 400


def test_history_api(client, design_id):
    with SessionLocal() as db:
        from app.agent.conversation import save_history
        save_history(db, design_id, [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "好的",
             "tool_calls": [{"id": "t", "name": "get_design_state", "arguments": {}}]},
            {"role": "tool", "tool_call_id": "t", "content": "{}"},
        ])
    hist = client.get(f"/api/designs/{design_id}/agent/history").json()
    assert len(hist) == 2                          # tool 消息不展示
    assert hist[1]["tool_calls"] == ["get_design_state"]

    assert client.delete(f"/api/designs/{design_id}/agent/history").status_code == 204
    assert client.get(f"/api/designs/{design_id}/agent/history").json() == []
