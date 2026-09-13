"""POST /api/chat：把對話丟給 LLM，以 SSE 逐段回傳。

事件格式（每行 `data: <json>`）：
  {"type":"text","text":"..."}   文字片段
  {"type":"done"}                 結束
  {"type":"error","message":"..."} 中途失敗
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.llm.bedrock import BedrockMessage, Streamer, to_bedrock_messages

router = APIRouter(prefix="/api")


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    system: str | None = None


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _events(streamer: Streamer, messages: list[BedrockMessage], system: str | None) -> Iterator[str]:
    try:
        for delta in streamer(messages, system):
            yield _sse({"type": "text", "text": delta})
        yield _sse({"type": "done"})
    except Exception as exc:  # noqa: BLE001 — 錯誤要回給前端顯示，不能讓串流默默斷掉
        yield _sse({"type": "error", "message": str(exc)})


@router.post("/chat")
def chat(req: ChatRequest, request: Request) -> StreamingResponse:
    messages = to_bedrock_messages([m.model_dump() for m in req.messages])
    if not messages:
        raise HTTPException(status_code=400, detail="conversation must contain a user message")
    streamer: Streamer = request.app.state.streamer
    return StreamingResponse(
        _events(streamer, messages, req.system),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
