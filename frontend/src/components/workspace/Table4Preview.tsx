import type { FC } from "react";

import type { CaseInput } from "@/agent/schema";
import { cn } from "@/lib/utils";

const fmtPrice = (v?: string) => (v ? Number(v).toLocaleString("zh-TW") : undefined);

type Cell = { value?: string; required?: boolean; computed?: boolean };

/**
 * 表4 上半部（列 4–8）的預覽。
 * 藍字＝使用者輸入；「缺」＝還沒提供；「待計算」＝之後由引擎填。
 */
export const Table4Preview: FC<{ input: CaseInput; className?: string }> = ({ input, className }) => {
  const cols = [
    { title: "比準地", sub: "宗地流水號 —" },
    ...input.comparables.map((c, i) => ({ title: `比較標的${i + 1}`, sub: `實例編號 ${c.caseNo ?? "—"}` })),
  ];
  const rows: { label: string; cells: Cell[] }[] = [
    {
      label: "0 基本資料（地號）",
      cells: [{ value: input.subject.parcel, required: true }, ...input.comparables.map((c) => ({ value: c.parcel, required: true }))],
    },
    {
      label: "土地正常單價",
      cells: [{}, ...input.comparables.map((c) => ({ value: fmtPrice(c.unitPrice), required: true }))],
    },
    {
      label: "交易日期",
      cells: [{ value: input.subject.baseDate, required: true }, ...input.comparables.map((c) => ({ value: c.tradeDate, required: true }))],
    },
    {
      label: "調整至估價基準日單價（元/㎡）",
      cells: [{ computed: true }, { computed: true }, { computed: true }, { computed: true }],
    },
    {
      label: "地價區段",
      cells: [{ value: input.subject.zone, required: true }, ...input.comparables.map((c) => ({ value: c.zone, required: true }))],
    },
  ];

  return (
    <div className={cn("overflow-x-auto", className)}>
      <table className="w-full min-w-[620px] border-separate border-spacing-0 text-sm">
        <thead>
          <tr>
            <th scope="col" className="rounded-ss-lg border-b border-border/60 bg-muted/60 px-3 py-2 text-start font-medium text-muted-foreground">
              調整項目
            </th>
            {cols.map((c, i) => (
              <th
                key={i}
                scope="col"
                className={cn(
                  "border-b border-s border-border/60 bg-muted/60 px-3 py-2 text-start font-medium",
                  i === cols.length - 1 && "rounded-se-lg",
                )}
              >
                <div>{c.title}</div>
                <div className="text-xs font-normal text-muted-foreground">{c.sub}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, ri) => (
            <tr key={ri}>
              <th scope="row" className="border-b border-border/40 px-3 py-2 text-start font-normal text-muted-foreground">
                {r.label}
              </th>
              {r.cells.map((cell, ci) => {
                const missing = cell.required && !cell.value;
                return (
                  <td
                    key={ci}
                    className={cn(
                      "border-b border-s border-border/40 px-3 py-2 tabular-nums",
                      cell.value ? "text-sky-400" : "text-muted-foreground/50",
                      missing && "bg-amber-400/10 text-amber-300",
                    )}
                  >
                    {cell.value ?? (cell.computed ? "待計算" : missing ? "缺" : "—")}
                  </td>
                );
              })}
            </tr>
          ))}
          <tr>
            <td colSpan={5} className="px-3 py-2 text-xs text-muted-foreground/70">
              列 9–34（個別因素調整、合計、權重、比準地地價）由計算引擎產出，前端測試階段留白。
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
};
