import { useAui } from "@assistant-ui/react";
import { ChevronDownIcon, FileSpreadsheetIcon, FolderIcon, ZapIcon } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";

import { CHAT_BACKEND } from "@/agent/backend";
import { parseCaseText } from "@/agent/parse";
import { type CaseInput, type ComparableInput, type SubjectInput, emptyCase, findMissing, mergeCase } from "@/agent/schema";
import { collectCase } from "@/agent/tools";
import { composeAnswer } from "@/components/tools/MissingFieldsCard";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { WORKSPACE_TABS, useWorkspace } from "@/components/workspace/context";

const chipClass = "inline-flex min-w-0 items-center gap-2 rounded-lg px-2 py-1 text-[13px] leading-[22px] whitespace-nowrap text-[#eee] hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none [&_svg]:size-4 [&_svg]:shrink-0";

export function ContextChips() {
  return (
    <div className="mx-3.5 flex h-12 shrink-0 items-start gap-2 rounded-t-[20px] bg-chip-strip px-1.5 pt-2 sm:gap-4">
      <CaseDataButton />
      <TemplatesButton />
    </div>
  );
}

function CaseDataButton() {
  const aui = useAui();
  const [input, setInput] = useState<CaseInput | null>(null);
  const open = () => setInput(mergeCase(collectCase(aui.thread().getState().messages), parseCaseText(aui.composer().getState().text)));
  return (
    <>
      <button type="button" className={chipClass} onClick={open} aria-haspopup="dialog"><FolderIcon />案件資料</button>
      {input && <Dialog title="案件資料" onClose={() => setInput(null)}><CaseForm input={input} onClose={() => setInput(null)} /></Dialog>}
    </>
  );
}

const allFields = findMissing(emptyCase());

function CaseForm({ input, onClose }: { input: CaseInput; onClose: () => void }) {
  const aui = useAui();
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(allFields.map((f) => [
    `${f.target}.${f.key}`,
    f.target === "subject" ? input.subject[f.key as keyof SubjectInput] ?? "" : input.comparables[Number(f.target.slice(-1)) - 1][f.key as keyof ComparableInput] ?? "",
  ])));
  const answer = composeAnswer(allFields, values);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!answer) return;
    const draft = aui.composer().getState().text.trimEnd();
    aui.composer().setText([draft, answer].filter(Boolean).join("\n\n"));
    onClose();
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-5">
      <p className="text-[13px] leading-5 text-muted-foreground">查看或補填目前的案件資料。確認後加入輸入框，可以繼續編輯再送出。</p>
      {["比準地", "比較標的1", "比較標的2", "比較標的3"].map((target) => (
        <fieldset key={target} className="flex flex-col gap-2.5">
          <legend className="mb-2 text-[13px] font-medium">{target}</legend>
          {allFields.filter((f) => f.targetLabel === target).map((f) => {
            const id = `${f.target}.${f.key}`;
            return (
              <label key={id} className="grid items-center gap-1.5 text-[13px] sm:grid-cols-[6.5rem_1fr]">
                <span className="text-muted-foreground">{f.label}</span>
                <input value={values[id]} placeholder={f.hint} onChange={(e) => setValues((v) => ({ ...v, [id]: e.target.value }))} className="h-9 min-w-0 rounded-lg bg-background px-3 text-base outline-none placeholder:text-muted-foreground/40 focus:ring-1 focus:ring-ring/50 sm:h-8 sm:text-[13px]" />
              </label>
            );
          })}
        </fieldset>
      ))}
      <div className="sticky bottom-0 flex items-center justify-between gap-3 bg-[#1c1c1c] py-3">
        <span className="text-xs text-muted-foreground">已填 {Object.values(values).filter((v) => v.trim()).length} / {allFields.length}</span>
        <Button type="submit" disabled={!answer} className="rounded-full text-[13px]">加入輸入框</Button>
      </div>
    </form>
  );
}

function TemplatesButton() {
  const [open, setOpen] = useState(false);
  const workspace = useWorkspace();
  return (
    <>
      <button type="button" className={chipClass} onClick={() => setOpen(true)} aria-haspopup="dialog"><FileSpreadsheetIcon />表格範本</button>
      {open && (
        <Dialog title="表格範本" onClose={() => setOpen(false)}>
          <p className="mb-4 text-sm text-muted-foreground">開啟空白範本預覽，或下載後填寫。</p>
          <div className="flex flex-col gap-3">
            {WORKSPACE_TABS.filter((t) => t.id !== "map").map((tab) => (
              <div key={tab.id} className="rounded-2xl bg-background p-4">
                <p className="mb-3 text-sm leading-6">{tab.label}</p>
                <div className="flex flex-wrap items-center gap-2">
                  <Button type="button" variant="secondary" size="sm" className="rounded-full" onClick={() => { setOpen(false); workspace.open(tab.id); }}>開啟預覽<span className="sr-only">{tab.short}</span></Button>
                  <a href={`/templates/${tab.id}.xlsx`} download={`${tab.label}.xlsx`} className="rounded-full px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-foreground">Excel<span className="sr-only"> {tab.short}</span></a>
                  <a href={`/templates/${tab.id}.pdf`} download={`${tab.label}.pdf`} className="rounded-full px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-foreground">PDF<span className="sr-only"> {tab.short}</span></a>
                </div>
              </div>
            ))}
          </div>
        </Dialog>
      )}
    </>
  );
}

export function ModelInfoButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" aria-label="模型資訊" title="查看模型資訊" aria-haspopup="dialog" onClick={() => setOpen(true)} className="inline-flex h-8 min-w-0 items-center gap-1.5 rounded-full px-2 text-[13px] text-[#f5f5f5] hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none">
        <ZapIcon className="size-4 shrink-0 fill-current" />
        <span className="hidden @min-[30rem]:inline">LandLens</span>
        <span className="hidden text-[#999] @min-[22rem]:inline">{CHAT_BACKEND === "mock" ? "模擬" : "Bedrock"}</span>
        <ChevronDownIcon className="size-3.5 shrink-0 text-[#999]" />
      </button>
      {open && <Dialog title="模型資訊" onClose={() => setOpen(false)}>{CHAT_BACKEND === "mock" ? <p className="text-sm leading-6 text-muted-foreground">目前使用前端模擬模式，以固定規則回覆，沒有連接 AI 模型。</p> : <ModelDetails />}</Dialog>}
    </>
  );
}

type ModelState = { status: "loading" } | { status: "error" } | { status: "ready"; model: string; region: string };

function ModelDetails() {
  const [state, setState] = useState<ModelState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    const timeout = window.setTimeout(() => controller.abort(), 8000);
    const read = async () => {
      try {
        const response = await fetch("/api/health", { signal: controller.signal, cache: "no-store" });
        if (!response.ok) throw new Error("Health request failed");
        const data: unknown = await response.json();
        if (!data || typeof data !== "object" || !("model" in data) || !("region" in data) || typeof data.model !== "string" || typeof data.region !== "string") throw new Error("Invalid model information");
        if (!cancelled) setState({ status: "ready", model: data.model, region: data.region });
      } catch {
        if (!cancelled) setState({ status: "error" });
      } finally { window.clearTimeout(timeout); }
    };
    void read();
    return () => { cancelled = true; controller.abort(); window.clearTimeout(timeout); };
  }, [attempt]);

  return (
    <div className="flex flex-col gap-4 text-sm">
      <p className="text-muted-foreground">LandLens 透過 AWS Bedrock 使用以下模型設定。</p>
      {state.status === "loading" && <p role="status" className="py-3 text-muted-foreground">正在讀取模型設定…</p>}
      {state.status === "error" && <div role="alert" className="rounded-xl bg-background p-4"><p className="mb-3 text-muted-foreground">無法取得模型設定，請確認後端服務已啟動。</p><Button type="button" variant="secondary" size="sm" onClick={() => { setState({ status: "loading" }); setAttempt((n) => n + 1); }}>重新讀取</Button></div>}
      {state.status === "ready" && <dl className="grid grid-cols-[5rem_1fr] gap-x-3 gap-y-4 rounded-2xl bg-background p-4"><dt className="text-muted-foreground">服務</dt><dd>AWS Bedrock</dd><dt className="text-muted-foreground">模型</dt><dd className="break-all">{state.model}</dd><dt className="text-muted-foreground">區域</dt><dd>{state.region}</dd></dl>}
    </div>
  );
}
