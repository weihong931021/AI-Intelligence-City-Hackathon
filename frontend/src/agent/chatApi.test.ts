import { describe, expect, it, vi } from "vitest";

import { streamChat } from "./chatApi";

function sseResponse(chunks: string[], status = 200): Response {
  const enc = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      for (const ch of chunks) c.enqueue(enc.encode(ch));
      c.close();
    },
  });
  return new Response(body, { status, headers: { "content-type": "text/event-stream" } });
}

async function collect(gen: AsyncIterable<string>): Promise<string[]> {
  const out: string[] = [];
  for await (const t of gen) out.push(t);
  return out;
}

describe("streamChat", () => {
  it("yields text deltas until done, even when a chunk splits an event", async () => {
    const fetcher = vi.fn(async () =>
      sseResponse(['data: {"type":"text","text":"你好"}\n\ndata: {"type":"te', 'xt","text":"，世界"}\n\ndata: {"type":"done"}\n\n']),
    );
    const out = await collect(streamChat({ messages: [{ role: "user", text: "hi" }] }, { fetcher }));
    expect(out).toEqual(["你好", "，世界"]);
  });

  it("POSTs messages and system prompt as JSON to /api/chat", async () => {
    const fetcher = vi.fn(async () => sseResponse(['data: {"type":"done"}\n\n']));
    await collect(streamChat({ messages: [{ role: "user", text: "hi" }], system: "你是助理" }, { fetcher }));
    const [url, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/chat");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ messages: [{ role: "user", text: "hi" }], system: "你是助理" });
  });

  it("throws with the server message on an error event", async () => {
    const fetcher = vi.fn(async () => sseResponse(['data: {"type":"text","text":"部分"}\n\ndata: {"type":"error","message":"bedrock down"}\n\n']));
    await expect(collect(streamChat({ messages: [{ role: "user", text: "hi" }] }, { fetcher }))).rejects.toThrow("bedrock down");
  });

  it("throws on a non-2xx response", async () => {
    const fetcher = vi.fn(async () => new Response("nope", { status: 502 }));
    await expect(collect(streamChat({ messages: [{ role: "user", text: "hi" }] }, { fetcher }))).rejects.toThrow(/502/);
  });
});
