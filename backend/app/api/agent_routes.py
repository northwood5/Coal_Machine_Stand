"""Agent 模式 API: LLM 设置 / 对话 (WebSocket 流式 + REST)"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.conversation import clear_history, load_history, save_history
from app.agent.orchestrator import run_agent_turn
from app.db import SessionLocal, get_db
from app.llm.base import LLMNotConfigured
from app.llm.settings import build_adapter, get_settings, save_settings

router = APIRouter(prefix="/api")


# ---------- LLM 设置 ----------

class LLMSettingsIn(BaseModel):
    provider: str                # anthropic | openai_compat
    model: str = ""
    base_url: str = ""
    api_key: str = ""            # 空 = 保留原 key


@router.get("/settings/llm")
def read_llm_settings(db: Session = Depends(get_db)):
    s = get_settings(db)
    masked = f"…{s.api_key[-4:]}" if s.api_key else ""
    return {"provider": s.provider, "model": s.model,
            "base_url": s.base_url, "api_key_masked": masked,
            "configured": bool(s.api_key)}


@router.put("/settings/llm")
def write_llm_settings(body: LLMSettingsIn, db: Session = Depends(get_db)):
    if body.provider not in ("anthropic", "openai_compat"):
        raise HTTPException(400, "provider 须为 anthropic 或 openai_compat")
    save_settings(db, body.provider, body.model, body.base_url, body.api_key or None)
    return read_llm_settings(db)


# ---------- 对话历史 ----------

def _display_history(messages: list[dict]) -> list[dict]:
    """过滤为前端可展示的消息 (省去 tool 明细)"""
    out = []
    for m in messages:
        if m["role"] == "user":
            out.append({"role": "user", "content": m["content"]})
        elif m["role"] == "assistant":
            item = {"role": "assistant", "content": m.get("content", "")}
            if m.get("tool_calls"):
                item["tool_calls"] = [tc["name"] for tc in m["tool_calls"]]
            out.append(item)
    return out


@router.get("/designs/{design_id}/agent/history")
def get_history(design_id: int, db: Session = Depends(get_db)):
    return _display_history(load_history(db, design_id))


@router.delete("/designs/{design_id}/agent/history", status_code=204)
def delete_history(design_id: int, db: Session = Depends(get_db)):
    clear_history(db, design_id)


# ---------- REST 对话 (非流式, 测试/脚本用) ----------

class ChatIn(BaseModel):
    message: str


@router.post("/designs/{design_id}/agent/chat")
def agent_chat(design_id: int, body: ChatIn, db: Session = Depends(get_db)):
    try:
        adapter = build_adapter(db)
    except LLMNotConfigured as e:
        raise HTTPException(409, str(e))
    history = load_history(db, design_id)
    events = list(run_agent_turn(db, adapter, design_id, history, body.message))
    save_history(db, design_id, history)
    return {"events": events}


# ---------- WebSocket 对话 (流式) ----------

@router.websocket("/designs/{design_id}/agent/ws")
async def agent_ws(ws: WebSocket, design_id: int):
    await ws.accept()
    db = SessionLocal()
    try:
        while True:
            data = await ws.receive_json()
            message = data.get("message", "")
            if not message:
                continue
            try:
                adapter = build_adapter(db)
            except LLMNotConfigured as e:
                await ws.send_json({"type": "error", "message": str(e)})
                continue

            history = load_history(db, design_id)
            gen = run_agent_turn(db, adapter, design_id, history, message)

            def next_event():
                try:
                    return next(gen)
                except StopIteration:
                    return None

            while True:
                event = await asyncio.to_thread(next_event)   # 同步生成器放线程池, 不阻塞事件循环
                if event is None:
                    break
                await ws.send_json(event)
            save_history(db, design_id, history)
    except WebSocketDisconnect:
        pass
    finally:
        db.close()
