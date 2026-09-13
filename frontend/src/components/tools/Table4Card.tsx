import { makeAssistantToolUI } from "@assistant-ui/react";
import { DownloadIcon, FileSpreadsheetIcon, MapIcon } from "lucide-react";
import type { FC } from "react";

import { RENDER_TABLE4_TOOL, type Table4Result } from "@/agent/tools";
import type { CaseInput } from "@/agent/schema";
import { useWorkspace } from "@/components/workspace/context";

/** 聊天欄裡的精簡摘要：內容在右側工作區看。 */
const Table4CardImpl: FC<{ args: CaseInput; result?: Table4Result; running: boolean }> = ({ args, result, running }) => {
  const ws = useWorkspace();
  return (
    <div className="my-3 overflow-hidden rounded-2xl bg-card">
      <div className="flex items-center gap-3 px-3.5 py-3">
        <FileSpreadsheetIcon className="size-4 shrink-0 text-emerald-400" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px]">表4 比較法調查估價表</div>
          <div className="truncate text-xs text-muted-foreground">
            {running ? "產生中…" : `比準地 ${args.subject.parcel ?? "—"}，3 個比較標的`}
          </div>
        </div>
      </div>
      {result && (
        <div className="flex flex-wrap items-center gap-1.5 px-2.5 pt-0.5 pb-2.5">
          <button
            type="button"
            onClick={() => ws.open("table4")}
            className="inline-flex h-7 items-center gap-1.5 rounded-full bg-accent px-2.5 text-xs text-foreground transition-colors hover:bg-secondary"
          >
            <FileSpreadsheetIcon className="size-3.5" />
            開啟表4
          </button>
          <button
            type="button"
            onClick={() => ws.open("map")}
            className="inline-flex h-7 items-center gap-1.5 rounded-full bg-accent px-2.5 text-xs text-foreground transition-colors hover:bg-secondary"
          >
            <MapIcon className="size-3.5" />
            位置圖
          </button>
          {result.downloads.map((d) => (
            <a
              key={d.href}
              href={d.href}
              download={d.filename}
              className="inline-flex h-7 items-center gap-1 rounded-full px-2 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <DownloadIcon className="size-3.5" />
              {d.label.split(" ")[0]}
            </a>
          ))}
        </div>
      )}
    </div>
  );
};

export const Table4ToolUI = makeAssistantToolUI<CaseInput, Table4Result>({
  toolName: RENDER_TABLE4_TOOL,
  render: ({ args, result, status }) => (
    <Table4CardImpl args={args} result={result} running={status.type === "running"} />
  ),
});
