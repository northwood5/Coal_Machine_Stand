"""Anthropic 适配器 (官方 SDK)。默认模型 claude-opus-4-8, 自适应思考。"""
from __future__ import annotations

from app.llm.base import LLMAdapter, LLMReply, ToolCallReq, ToolDef

DEFAULT_MODEL = "claude-opus-4-8"


class AnthropicAdapter(LLMAdapter):
    def __init__(self, api_key: str, model: str = "", base_url: str = ""):
        import anthropic  # 延迟导入, 未配置该厂商时不要求安装

        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = anthropic.Anthropic(**kwargs)
        self._model = model or DEFAULT_MODEL

    def _to_anthropic_messages(self, messages: list[dict]) -> list[dict]:
        """中立格式 → Anthropic 格式。连续 tool 结果合并进同一条 user 消息。"""
        out: list[dict] = []
        pending_results: list[dict] = []

        def flush_results():
            if pending_results:
                out.append({"role": "user", "content": list(pending_results)})
                pending_results.clear()

        for m in messages:
            if m["role"] == "user":
                flush_results()
                out.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant":
                flush_results()
                content: list[dict] = []
                if m.get("content"):
                    content.append({"type": "text", "text": m["content"]})
                for tc in m.get("tool_calls", []):
                    content.append({"type": "tool_use", "id": tc["id"],
                                    "name": tc["name"], "input": tc["arguments"]})
                out.append({"role": "assistant", "content": content or m.get("content", "")})
            elif m["role"] == "tool":
                pending_results.append({"type": "tool_result",
                                        "tool_use_id": m["tool_call_id"],
                                        "content": m["content"]})
        flush_results()
        return out

    def chat(self, system: str, messages: list[dict], tools: list[ToolDef]) -> LLMReply:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=system,
            messages=self._to_anthropic_messages(messages),
            tools=[{"name": t.name, "description": t.description,
                    "input_schema": t.input_schema} for t in tools],
        )
        text = ""
        tool_calls: list[ToolCallReq] = []
        for block in resp.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCallReq(id=block.id, name=block.name,
                                              arguments=dict(block.input)))
        return LLMReply(text=text, tool_calls=tool_calls, stop_reason=resp.stop_reason or "")
