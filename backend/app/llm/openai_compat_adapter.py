"""OpenAI 兼容适配器 (httpx 直连 /chat/completions)。

覆盖 DeepSeek / Qwen / GLM 等提供 OpenAI 兼容端点的国产模型。
"""
from __future__ import annotations

import json

import httpx

from app.llm.base import LLMAdapter, LLMReply, ToolCallReq, ToolDef


class OpenAICompatAdapter(LLMAdapter):
    def __init__(self, api_key: str, model: str, base_url: str):
        if not base_url:
            raise ValueError("OpenAI 兼容模式必须提供 base_url")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")

    def _to_openai_messages(self, system: str, messages: list[dict]) -> list[dict]:
        out: list[dict] = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "user":
                out.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant":
                item: dict = {"role": "assistant", "content": m.get("content") or None}
                if m.get("tool_calls"):
                    item["tool_calls"] = [
                        {"id": tc["id"], "type": "function",
                         "function": {"name": tc["name"],
                                      "arguments": json.dumps(tc["arguments"], ensure_ascii=False)}}
                        for tc in m["tool_calls"]
                    ]
                out.append(item)
            elif m["role"] == "tool":
                out.append({"role": "tool", "tool_call_id": m["tool_call_id"],
                            "content": m["content"]})
        return out

    def chat(self, system: str, messages: list[dict], tools: list[ToolDef]) -> LLMReply:
        payload: dict = {
            "model": self._model,
            "messages": self._to_openai_messages(system, messages),
        }
        if tools:
            payload["tools"] = [
                {"type": "function",
                 "function": {"name": t.name, "description": t.description,
                              "parameters": t.input_schema}}
                for t in tools
            ]
        resp = httpx.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json=payload, timeout=300.0,
        )
        resp.raise_for_status()
        data = resp.json()
        msg = data["choices"][0]["message"]
        tool_calls = [
            ToolCallReq(id=tc["id"], name=tc["function"]["name"],
                        arguments=json.loads(tc["function"]["arguments"] or "{}"))
            for tc in (msg.get("tool_calls") or [])
        ]
        return LLMReply(text=msg.get("content") or "", tool_calls=tool_calls,
                        stop_reason=data["choices"][0].get("finish_reason", ""))
