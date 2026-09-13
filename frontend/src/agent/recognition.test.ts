import type { ThreadMessage } from "@assistant-ui/react";
import { describe, expect, it } from "vitest";
import { collectCase, RECOGNIZE_DOCUMENT_TOOL } from "./tools";

const user = (text: string, ids: string[] = []): ThreadMessage => ({ role: "user", content: [{ type: "text", text }], attachments: ids.map((id) => ({ id, name: "案件.pdf", content: [] })) }) as unknown as ThreadMessage;
const recognized = (id: string): ThreadMessage => ({ role: "assistant", content: [{ type: "tool-call", toolName: RECOGNIZE_DOCUMENT_TOOL, result: { attachmentId: id, kind: "case", fields: [{ target: "subject", key: "parcel", value: "新北市樹林區樹德段1415地號", source: "第1頁", evidence: "新北市樹林區樹德段1415地號" }, { target: "comparable-1", key: "unitPrice", value: "130,167", source: "第1頁", evidence: "130,167" }] } }] }) as unknown as ThreadMessage;

describe("recognized document fields", () => {
  it("uses identified fields on an attachment-only turn and keeps them on follow-up", () => {
    const input = collectCase([user("", ["pdf"]), recognized("pdf"), user("比準地：估價基準日 111年9月1日")]);
    expect(input.subject).toEqual({ parcel: "新北市樹林區樹德段1415地號", baseDate: "111年9月1日" });
    expect(input.comparables[0].unitPrice).toBe("130167");
  });
  it("lets the user's same-turn corrections override imported values", () => {
    const input = collectCase([user("比準地：地號 新北市樹林區樹德段1416地號", ["pdf"]), recognized("pdf")]);
    expect(input.subject.parcel).toBe("新北市樹林區樹德段1416地號");
  });
  it("does not import recognition results detached from their source message", () => {
    expect(collectCase([user(""), recognized("removed")]).subject).toEqual({});
  });
});
