/**
 * 後端 `POST /api/chat` 的 SSE client。
 * 事件：{type:"text",text} 逐段文字、{type:"done"} 結束、{type:"error",message} 失敗。
 */

export type ChatRole = "user" | "assistant";
export type ChatMessage = { role: ChatRole; text: string };
export type ChatRequest = { messages: ChatMessage[]; system?: string };

type ChatEvent = { type: "text"; text: string } | { type: "done" } | { type: "error"; message: string };

export type StreamChatOptions = {
  signal?: AbortSignal;
  /** 測試注入用；預設用全域 fetch。 */
  fetcher?: typeof fetch;
  url?: string;
};

export async function* streamChat(req: ChatRequest, opts: StreamChatOptions = {}): AsyncGenerator<string> {
  const fetcher = opts.fetcher ?? fetch;
  const res = await fetcher(opts.url ?? "/api/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(req),
    signal: opts.signal,
  });
  if (!res.ok || !res.body) throw new Error(`chat API 回應 ${res.status}`);

  for await (const ev of parseSse(res.body)) {
    if (ev.type === "text") yield ev.text;
    else if (ev.type === "error") throw new Error(ev.message);
    else if (ev.type === "done") return;
  }
}

/** 以空行切事件；chunk 可能切在事件中間，所以要累積 buffer。 */
async function* parseSse(body: ReadableStream<Uint8Array>): AsyncGenerator<ChatEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx = buf.indexOf("\n\n");
      while (idx >= 0) {
        const block = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        const data = block
          .split("\n")
          .filter((l) => l.startsWith("data: "))
          .map((l) => l.slice("data: ".length))
          .join("\n");
        if (data) yield JSON.parse(data) as ChatEvent;
        idx = buf.indexOf("\n\n");
      }
    }
  } finally {
    reader.releaseLock();
  }
}
