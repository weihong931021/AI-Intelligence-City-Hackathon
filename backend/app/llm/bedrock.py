"""Bedrock Converse 串流封裝。只負責「訊息格式轉換」與「逐字吐出」。"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Any

BedrockMessage = dict[str, Any]
# (messages, system) -> 逐段文字
Streamer = Callable[[list[BedrockMessage], str | None], Iterator[str]]


def to_bedrock_messages(messages: Iterable[Mapping[str, str]]) -> list[BedrockMessage]:
    """轉成 Converse API 格式：去掉空白訊息、去掉開頭的 assistant、合併連續同角色（Converse 要求交錯）。"""
    out: list[BedrockMessage] = []
    for m in messages:
        text = (m.get("text") or "").strip()
        if not text:
            continue
        role = m["role"]
        if not out and role != "user":
            continue
        if out and out[-1]["role"] == role:
            out[-1]["content"][0]["text"] += "\n" + text
        else:
            out.append({"role": role, "content": [{"text": text}]})
    return out


def make_bedrock_streamer(model_id: str, region: str, max_tokens: int = 1024) -> Streamer:
    """回傳一個 Streamer；client 延遲到第一次呼叫才建立，import 時不需要憑證。"""
    client: Any = None

    def stream(messages: list[BedrockMessage], system: str | None) -> Iterator[str]:
        nonlocal client
        if client is None:
            import boto3

            client = boto3.client("bedrock-runtime", region_name=region)
        kwargs: dict[str, Any] = {
            "modelId": model_id,
            "messages": messages,
            "inferenceConfig": {"maxTokens": max_tokens},
        }
        if system:
            kwargs["system"] = [{"text": system}]
        for event in client.converse_stream(**kwargs)["stream"]:
            delta = event.get("contentBlockDelta", {}).get("delta", {}).get("text")
            if delta:
                yield delta

    return stream
