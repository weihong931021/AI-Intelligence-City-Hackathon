import { makeAssistantToolUI } from "@assistant-ui/react";
import { FileCheckIcon } from "lucide-react";

import type { DocumentRecognition } from "@/agent/recognition";
import { COMPARABLE_FIELDS, SUBJECT_FIELDS } from "@/agent/schema";
import { RECOGNIZE_DOCUMENT_TOOL } from "@/agent/tools";

const labels = Object.fromEntries([...SUBJECT_FIELDS, ...COMPARABLE_FIELDS].map((f) => [f.key, f.label]));

export const DocumentRecognitionToolUI = makeAssistantToolUI<{ filename: string }, DocumentRecognition>({
  toolName: RECOGNIZE_DOCUMENT_TOOL,
  render: ({ result }) => {
    if (!result) return null;
    const count = result.fields.length;
    return (
      <div className="my-3 rounded-2xl bg-card p-3.5 text-[13px] leading-5" aria-label="文件辨識結果">
        <div className="mb-2 flex items-center gap-2 font-medium"><FileCheckIcon className="size-4 shrink-0" />{count ? `已辨識並帶入 ${count} 個欄位` : result.kind === "template" ? "已辨識：空白範本" : "已辨識文件"}</div>
        <p className="font-medium">{result.title}</p>
        <p className="mt-1 text-muted-foreground">{result.summary}</p>
        <p className="mt-2 truncate text-xs text-muted-foreground" title={result.filename}>{result.filename}</p>
        {count > 0 && <details className="mt-3"><summary className="cursor-pointer text-muted-foreground hover:text-foreground">查看欄位與來源</summary><div className="mt-3 space-y-3">{result.fields.map((field) => <div key={`${field.target}.${field.key}`}><p className="text-xs text-muted-foreground">{field.target === "subject" ? "比準地" : `比較標的${field.target.slice(-1)}`} · {labels[field.key]}</p><p className="break-words">{field.value}</p><p className="text-xs text-muted-foreground">{field.source}</p></div>)}</div></details>}
        {result.warnings.length > 0 && <details className="mt-3 text-xs text-amber-200/80"><summary className="cursor-pointer">辨識提醒（{result.warnings.length}）</summary><ul className="mt-2 space-y-1">{result.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></details>}
      </div>
    );
  },
});
