import json

from fastapi.testclient import TestClient

from app.llm.bedrock import to_bedrock_messages
from app.main import create_app


def sse_events(response):
    return [json.loads(line[len("data: ") :]) for line in response.iter_lines() if line.startswith("data: ")]


def test_to_bedrock_messages_drops_empty_and_leading_assistant():
    out = to_bedrock_messages(
        [
            {"role": "assistant", "text": "歡迎"},
            {"role": "user", "text": "   "},
            {"role": "user", "text": "你好"},
        ]
    )
    assert out == [{"role": "user", "content": [{"text": "你好"}]}]


def test_to_bedrock_messages_merges_consecutive_same_role():
    out = to_bedrock_messages(
        [
            {"role": "user", "text": "a"},
            {"role": "user", "text": "b"},
            {"role": "assistant", "text": "c"},
            {"role": "user", "text": "d"},
        ]
    )
    assert out == [
        {"role": "user", "content": [{"text": "a\nb"}]},
        {"role": "assistant", "content": [{"text": "c"}]},
        {"role": "user", "content": [{"text": "d"}]},
    ]


def test_chat_streams_text_events_then_done():
    seen = {}

    def fake_streamer(messages, system):
        seen["messages"], seen["system"] = messages, system
        yield "你好"
        yield "，世界"

    client = TestClient(create_app(streamer=fake_streamer))
    with client.stream(
        "POST", "/api/chat", json={"messages": [{"role": "user", "text": "hi"}], "system": "你是助理"}
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        events = sse_events(r)

    assert events == [{"type": "text", "text": "你好"}, {"type": "text", "text": "，世界"}, {"type": "done"}]
    assert seen["messages"] == [{"role": "user", "content": [{"text": "hi"}]}]
    assert seen["system"] == "你是助理"


def test_chat_emits_error_event_when_streamer_fails():
    def broken_streamer(messages, system):
        yield "部分"
        raise RuntimeError("bedrock down")

    client = TestClient(create_app(streamer=broken_streamer))
    with client.stream("POST", "/api/chat", json={"messages": [{"role": "user", "text": "hi"}]}) as r:
        events = sse_events(r)

    assert events == [{"type": "text", "text": "部分"}, {"type": "error", "message": "bedrock down"}]


def test_chat_rejects_conversation_without_user_message():
    def never(messages, system):
        raise AssertionError("must not be called")
        yield  # pragma: no cover

    client = TestClient(create_app(streamer=never))
    r = client.post("/api/chat", json={"messages": [{"role": "assistant", "text": "hi"}]})
    assert r.status_code == 400
