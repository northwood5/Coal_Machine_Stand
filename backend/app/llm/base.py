"""LLM 适配器统一接口 (可插拔层)。

编排层只面对本接口, 不感知具体厂商。中立消息格式:
  {"role": "user", "content": str}
  {"role": "assistant", "content": str, "tool_calls": [{"id","name","arguments"}]}
  {"role": "tool", "tool_call_id": str, "content": str}
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ToolDef:
    name: str
    description: str
    input_schema: dict          # JSON Schema


@dataclass
class ToolCallReq:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMReply:
    text: str = ""
    tool_calls: list[ToolCallReq] = field(default_factory=list)
    stop_reason: str = ""


class LLMAdapter(ABC):
    @abstractmethod
    def chat(self, system: str, messages: list[dict], tools: list[ToolDef]) -> LLMReply:
        """一次模型调用。messages 为中立格式, 返回文本与工具调用请求。"""


class LLMNotConfigured(Exception):
    pass
