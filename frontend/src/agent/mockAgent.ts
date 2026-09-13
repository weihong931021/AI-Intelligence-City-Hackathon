import type { ChatModelAdapter, ChatModelRunOptions } from "@assistant-ui/react";

import { type CaseInput, type MissingField, findMissing } from "./schema";
import {
  ASK_MISSING_TOOL,
  type LatLng,
  RENDER_TABLE4_TOOL,
  type Table4Result,
  collectCase,
  userText,
} from "./tools";

export { ASK_MISSING_TOOL, RENDER_TABLE4_TOOL, collectCase };
export type { LatLng, Table4Result };

export type AskMissingArgs = { missing: MissingField[]; collected: CaseInput };

/** 樹林區一帶的假座標，之後接後端再換成真的。 */
const FAKE_SUBJECT: LatLng = { lat: 24.9905, lng: 121.4236, label: "比準地" };
const FAKE_COMPARABLES: [number, number][] = [
  [24.9932, 121.4198],
  [24.9871, 121.4281],
  [24.9948, 121.4302],
];

function sleep(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(t);
      reject(new DOMException("aborted", "AbortError"));
    });
  });
}

export function buildResult(input: CaseInput): Table4Result {
  return {
    downloads: [
      { sheet: "table3", label: "表3 地價區段勘查表", href: "/templates/table3.xlsx", filename: "表3地價區段勘查表.xlsx" },
      { sheet: "table4", label: "表4 比較法調查估價表", href: "/templates/table4.xlsx", filename: "表4比較法調查估價表.xlsx" },
      {
        sheet: "table5",
        label: "表5 影響地價區域因素分析明細表",
        href: "/templates/table5.xlsx",
        filename: "表5影響地價區域因素分析明細表(住宅用地).xlsx",
      },
    ],
    map: {
      center: FAKE_SUBJECT,
      subject: { ...FAKE_SUBJECT, label: `比準地 ${input.subject.parcel ?? ""}` },
      comparables: FAKE_COMPARABLES.map(([lat, lng], i) => ({
        lat,
        lng,
        label: `比較標的${i + 1} ${input.comparables[i].parcel ?? ""}`,
      })),
    },
    note: "目前為前端測試模式：三張表直接輸出空白官方範本，地圖座標為假資料。",
  };
}

function missingSummary(missing: MissingField[]): string {
  const groups = new Map<string, string[]>();
  for (const m of missing) {
    const list = groups.get(m.targetLabel) ?? [];
    list.push(m.label);
    groups.set(m.targetLabel, list);
  }
  const lines = [...groups.entries()].map(([target, labels]) => `- **${target}**：${labels.join("、")}`);
  return `還缺 ${missing.length} 項資料，補齊後我就能填表：\n\n${lines.join("\n")}\n\n可以直接在下方表單填，或用文字回覆，例如「比準地：估價基準日 111年9月1日」。`;
}

/**
 * 純前端的假 agent：不打任何 API。
 * 讀取整段對話 → 合併輸入 → 缺就回問，齊就輸出表4 卡片。
 */
export const mockCaseAgent: ChatModelAdapter = {
  async *run({ messages, abortSignal }: ChatModelRunOptions) {
    const input = collectCase(messages);
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    const lastText = lastUser ? userText(lastUser).trim() : "";
    if (lastUser?.role === "user" && lastUser.attachments?.length) {
      yield { content: [{ type: "text", text: "目前是前端模擬模式，尚未連接文件辨識模型。請使用 Bedrock 模式辨識附件；這些文件不會被當成已辨識的案件資料。" }] };
      return;
    }
    const missing = findMissing(input);
    const touched = missing.length < 18; // 至少抓到一個欄位

    yield { content: [{ type: "text", text: "正在解析輸入…" }] };
    await sleep(500, abortSignal);

    if (!touched) {
      // 什麼都還沒抓到：直接給完整表單（輸入是固定的 18 格），不用先猜格式。
      const args: AskMissingArgs = { missing, collected: input };
      yield {
        content: [
          {
            type: "text",
            text:
              `我負責填「表4 比較法調查估價表」。直接在下方表單填**比準地** 3 項與 **3 個比較標的** 各 5 項，` +
              `或按輸入框的「載入範例」帶入一組資料。` +
              (lastText ? `\n\n（你剛才的輸入我沒有辨識出任何欄位。）` : ""),
          },
          {
            type: "tool-call",
            toolCallId: `ask-${Date.now()}`,
            toolName: ASK_MISSING_TOOL,
            args,
            argsText: JSON.stringify(args),
            result: { ok: true },
          },
        ],
      };
      return;
    }

    if (missing.length > 0) {
      const toolCallId = `ask-${Date.now()}`;
      const args: AskMissingArgs = { missing, collected: input };
      yield {
        content: [
          { type: "text", text: missingSummary(missing) },
          {
            type: "tool-call",
            toolCallId,
            toolName: ASK_MISSING_TOOL,
            args,
            argsText: JSON.stringify(args),
            result: { ok: true },
          },
        ],
      };
      return;
    }

    yield { content: [{ type: "text", text: "資料齊全，正在產生表4 與地圖…" }] };
    await sleep(700, abortSignal);

    const toolCallId = `t4-${Date.now()}`;
    const result = buildResult(input);
    yield {
      content: [
        {
          type: "text",
          text: `資料齊全。表4 預覽、位置圖與三張表已放到右側面板，也可以直接在這裡下載。`,
        },
        {
          type: "tool-call",
          toolCallId,
          toolName: RENDER_TABLE4_TOOL,
          args: input,
          argsText: JSON.stringify(input),
          result,
        },
      ],
    };
  },
};
