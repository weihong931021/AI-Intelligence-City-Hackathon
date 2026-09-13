import type { ChatModelRunOptions, ChatModelRunResult, ThreadMessage } from "@assistant-ui/react";
import { describe, expect, it } from "vitest";

import { type ChatStreamer, createApiCaseAgent } from "./apiAgent";
import type { ChatRequest } from "./chatApi";
import { ASK_MISSING_TOOL, RECOGNIZE_DOCUMENT_TOOL, RENDER_TABLE4_TOOL } from "./tools";
import type { DocumentRecognizer, Recognition } from "./recognition";
import { SAMPLE_CASE_TEXT, SAMPLE_PARTIAL_TEXT } from "./sample";

function user(text: string): ThreadMessage {
  return { role: "user", content: [{ type: "text", text }] } as unknown as ThreadMessage;
}

function fakeStream(chunks: string[], seen: { req?: ChatRequest } = {}, fail?: string): ChatStreamer {
  return async function* (req) {
    seen.req = req;
    for (const c of chunks) yield c;
    if (fail) throw new Error(fail);
  };
}

async function runAll(stream: ChatStreamer, messages: ThreadMessage[], extract?: DocumentRecognizer): Promise<ChatModelRunResult[]> {
  const agent = createApiCaseAgent({ stream, extract });
  const opts = { messages, abortSignal: new AbortController().signal } as unknown as ChatModelRunOptions;
  const out: ChatModelRunResult[] = [];
  for await (const r of agent.run(opts)) out.push(r);
  return out;
}

const textOf = (r: ChatModelRunResult) =>
  (r.content ?? []).filter((p) => p.type === "text").map((p) => (p as { text: string }).text).join("");
const toolCalls = (r: ChatModelRunResult) => (r.content ?? []).filter((p) => p.type === "tool-call");

describe("apiCaseAgent", () => {
  it("streams the model reply as accumulating text, then attaches the full form when nothing was recognised", async () => {
    const out = await runAll(fakeStream(["嗨", "，我是助理"]), [user("你好")]);
    expect(out.map(textOf)).toEqual(["嗨", "嗨，我是助理", "嗨，我是助理"]);
    const calls = toolCalls(out.at(-1)!);
    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({ toolName: ASK_MISSING_TOOL });
    expect((calls[0] as unknown as { args: { missing: unknown[] } }).args.missing).toHaveLength(18);
  });

  it("sends the text conversation plus a Traditional-Chinese system prompt to the backend", async () => {
    const seen: { req?: ChatRequest } = {};
    await runAll(fakeStream(["ok"], seen), [user("你好")]);
    expect(seen.req?.messages).toEqual([{ role: "user", text: "你好" }]);
    expect(seen.req?.system).toContain("繁體中文");
    expect(seen.req?.system).toContain("表4");
  });

  it("appends ask_missing_fields and tells the model which fields are missing", async () => {
    const seen: { req?: ChatRequest } = {};
    const out = await runAll(fakeStream(["還缺三項"], seen), [user(SAMPLE_PARTIAL_TEXT)]);
    const last = out.at(-1)!;
    expect(textOf(last)).toBe("還缺三項");
    const [call] = toolCalls(last) as unknown as { toolName: string; args: { missing: unknown[] } }[];
    expect(call.toolName).toBe(ASK_MISSING_TOOL);
    expect(call.args.missing).toHaveLength(3);
    expect(seen.req?.system).toContain("估價基準日");
  });

  it("recognizes attachment-only messages and asks only for fields missing from the document", async () => {
    const seen: { req?: ChatRequest } = {};
    const message = { ...user(""), attachments: [{ id: "doc", name: "案件.csv", type: "document", status: { type: "complete" }, content: [{ type: "text", text: SAMPLE_CASE_TEXT }] }] } as unknown as ThreadMessage;
    const recognition: Recognition = { kind: "case", title: "表4", summary: "已讀取案件", warnings: [], fields: [{ target: "subject", key: "parcel", value: "新北市樹林區樹德段1415地號", source: "第1頁", evidence: "新北市樹林區樹德段1415地號" }] };
    const out = await runAll(fakeStream(["已辨識文件"], seen), [message], async () => recognition);
    expect(seen.req?.messages).toEqual([{ role: "user", text: SAMPLE_CASE_TEXT }]);
    expect(toolCalls(out.at(-1)!)[0]).toMatchObject({ toolName: RECOGNIZE_DOCUMENT_TOOL });
    const missing = toolCalls(out.at(-1)!).find((p) => p.toolName === ASK_MISSING_TOOL)!;
    expect(missing.args).toMatchObject({ collected: { subject: { parcel: "新北市樹林區樹德段1415地號" } } });
    expect((missing.args as { missing: unknown[] }).missing).toHaveLength(17);
  });

  it("identifies blank templates without showing an unrelated full case form", async () => {
    const message = { ...user(""), attachments: [{ id: "blank", name: "表4.xlsx", content: [{ type: "text", text: "比較標的1 實例編號：" }] }] } as unknown as ThreadMessage;
    const out = await runAll(fakeStream(["這是空白表4範本"]), [message], async () => ({ kind: "template", title: "表4", summary: "空白範本", fields: [], warnings: [] }));
    expect(toolCalls(out.at(-1)!).map((p) => p.toolName)).toEqual([RECOGNIZE_DOCUMENT_TOOL]);
  });

  it("reports recognition failures instead of claiming no case data was provided", async () => {
    const message = { ...user(""), attachments: [{ id: "scan", name: "掃描.pdf", content: [{ type: "text", text: "掃描頁" }] }] } as unknown as ThreadMessage;
    const seen: { req?: ChatRequest } = {};
    const out = await runAll(fakeStream(["不應呼叫"], seen), [message], async () => { throw new Error("模型連線失敗"); });
    expect(textOf(out.at(-1)!)).toContain("辨識失敗");
    expect(seen.req).toBeUndefined();
    expect(toolCalls(out.at(-1)!)).toHaveLength(0);
  });

  it("appends render_table4 with the collected case when the input is complete", async () => {
    const out = await runAll(fakeStream(["收到"]), [user(SAMPLE_CASE_TEXT)]);
    const [call] = toolCalls(out.at(-1)!) as unknown as {
      toolName: string;
      args: { subject: { parcel: string } };
      result: { downloads: unknown[] };
    }[];
    expect(call.toolName).toBe(RENDER_TABLE4_TOOL);
    expect(call.args.subject.parcel).toBe("新北市樹林區樹德段1415地號");
    expect(call.result.downloads).toHaveLength(3);
  });

  it("shows a readable error instead of throwing when the backend fails mid-stream", async () => {
    const out = await runAll(fakeStream(["部分"], {}, "bedrock down"), [user("你好")]);
    expect(textOf(out.at(-1)!)).toContain("部分");
    expect(textOf(out.at(-1)!)).toContain("bedrock down");
  });
});
