/**
 * 前端 tool 名稱、結果型別，與從對話狀態抽資料的選擇器。
 * mockAgent 與 apiAgent 共用；UI 端只 import 這裡，不碰 agent 本體。
 */
import type { ThreadMessage } from "@assistant-ui/react";

import { parseCaseText } from "./parse";
import { type CaseInput, emptyCase, mergeCase } from "./schema";
import { type DocumentRecognition, recognitionToCase } from "./recognition";

export const RENDER_TABLE4_TOOL = "render_table4";
export const ASK_MISSING_TOOL = "ask_missing_fields";
export const RECOGNIZE_DOCUMENT_TOOL = "recognize_document";

export type LatLng = { lat: number; lng: number; label: string };

export type Table4Result = {
  downloads: { label: string; href: string; filename: string; sheet: "table3" | "table4" | "table5" }[];
  map: { center: LatLng; subject: LatLng; comparables: LatLng[] };
  note: string;
};

export function userText(m: ThreadMessage): string {
  return m.content
    .filter((p): p is { type: "text"; text: string } => p.type === "text")
    .map((p) => p.text)
    .join("\n");
}

/** 把整段對話的使用者輸入依序合併成一份案件。 */
export function collectCase(messages: readonly ThreadMessage[]): CaseInput {
  let acc = emptyCase();
  const documents = recognizedDocuments(messages);
  for (const m of messages) {
    if (m.role !== "user") continue;
    for (const attachment of m.attachments ?? []) {
      const result = documents.get(attachment.id);
      if (result) acc = mergeCase(acc, recognitionToCase(result));
    }
    // 使用者在同一則訊息或後續訊息的更正優先於文件。
    acc = mergeCase(acc, parseCaseText(userText(m)));
  }
  return acc;
}

export function recognizedDocuments(messages: readonly ThreadMessage[]): Map<string, DocumentRecognition> {
  const documents = new Map<string, DocumentRecognition>();
  for (const message of messages) {
    if (message.role !== "assistant") continue;
    for (const part of message.content) {
      if (part.type !== "tool-call" || part.toolName !== RECOGNIZE_DOCUMENT_TOOL || !part.result) continue;
      const result = part.result as DocumentRecognition;
      if (typeof result.attachmentId === "string" && Array.isArray(result.fields)) documents.set(result.attachmentId, result);
    }
  }
  return documents;
}

/** 找出最後一次成功產生的表4（右側工作區用）。 */
export function findLatestTable4(
  messages: readonly ThreadMessage[],
): { id: string; args: CaseInput; result: Table4Result } | undefined {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role !== "assistant") continue;
    for (const p of m.content) {
      if (p.type === "tool-call" && p.toolName === RENDER_TABLE4_TOOL && p.result) {
        return { id: p.toolCallId, args: p.args as CaseInput, result: p.result as Table4Result };
      }
    }
  }
  return undefined;
}
