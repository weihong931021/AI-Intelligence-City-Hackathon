import { makeAssistantToolUI, useAui } from "@assistant-ui/react";
import { type FC, type FormEvent, useState } from "react";

import { ASK_MISSING_TOOL, type AskMissingArgs } from "@/agent/mockAgent";
import type { MissingField } from "@/agent/schema";
import { Button } from "@/components/ui/button";

/** 把表單答案組成 parser 看得懂的文字，例如「比準地：估價基準日 111年9月1日」。 */
export function composeAnswer(missing: MissingField[], values: Record<string, string>): string {
  const byTarget = new Map<string, string[]>();
  for (const m of missing) {
    const v = values[`${m.target}.${m.key}`]?.trim();
    if (!v) continue;
    const list = byTarget.get(m.targetLabel) ?? [];
    list.push(`${m.label} ${v}`);
    byTarget.set(m.targetLabel, list);
  }
  return [...byTarget.entries()].map(([t, parts]) => `${t}：${parts.join("、")}`).join("\n");
}

const MissingFieldsForm: FC<{ missing: MissingField[]; disabled: boolean }> = ({ missing, disabled }) => {
  const aui = useAui();
  const [values, setValues] = useState<Record<string, string>>({});
  const [sent, setSent] = useState(false);

  const groups = new Map<string, MissingField[]>();
  for (const m of missing) groups.set(m.targetLabel, [...(groups.get(m.targetLabel) ?? []), m]);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const text = composeAnswer(missing, values);
    if (!text) return;
    setSent(true);
    aui.thread().append(text);
  };

  const filled = Object.values(values).filter((v) => v.trim()).length;

  return (
    <form onSubmit={onSubmit} className="my-3 flex flex-col gap-3.5 rounded-2xl bg-card p-3.5">
      {[...groups.entries()].map(([target, fields]) => (
        <fieldset key={target} className="flex flex-col gap-2">
          <legend className="mb-1 text-[13px] font-medium">{target}</legend>
          {fields.map((f) => {
            const id = `${f.target}.${f.key}`;
            return (
              <div key={id} className="grid grid-cols-[6.5rem_1fr] items-center gap-2">
                <label htmlFor={id} className="text-[13px] text-muted-foreground">
                  {f.label}
                </label>
                <input
                  id={id}
                  name={id}
                  disabled={disabled || sent}
                  placeholder={f.hint}
                  value={values[id] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [id]: e.target.value }))}
                  className="h-9 min-w-0 rounded-lg bg-background px-3 text-base outline-none placeholder:text-muted-foreground/50 focus:ring-1 focus:ring-muted-foreground/40 disabled:opacity-60 sm:h-8 sm:text-[13px]"
                />
              </div>
            );
          })}
        </fieldset>
      ))}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">
          已填 {filled} / {missing.length}（可以先填一部分再送）
        </span>
        <Button type="submit" size="sm" className="rounded-full px-4 text-[13px]" disabled={disabled || sent || filled === 0}>
          {sent ? "已送出" : "補上這些資料"}
        </Button>
      </div>
    </form>
  );
};

export const MissingFieldsToolUI = makeAssistantToolUI<AskMissingArgs, { ok: boolean }>({
  toolName: ASK_MISSING_TOOL,
  render: ({ args, status }) => (
    <MissingFieldsForm missing={args.missing ?? []} disabled={status.type === "running"} />
  ),
});
