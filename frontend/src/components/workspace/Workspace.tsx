import {
  ArrowLeftIcon,
  ArrowRightIcon,
  DownloadIcon,
  EllipsisVerticalIcon,
  FileSpreadsheetIcon,
  FileTextIcon,
  MapIcon,
  PanelLeftIcon,
  RotateCwIcon,
  XIcon,
} from "lucide-react";
import { type ComponentProps, type FC, type ReactNode, useEffect, useRef, useState } from "react";

import type { CaseInput } from "@/agent/schema";
import type { Table4Result } from "@/agent/tools";
import { CaseMap } from "@/components/workspace/CaseMap";
import { PdfViewer } from "@/components/workspace/PdfViewer";
import { WORKSPACE_TABS, type WorkspaceTab, useWorkspace } from "@/components/workspace/context";
import { cn } from "@/lib/utils";

const DEFAULT_CENTER = { lat: 24.9905, lng: 121.4236, label: "樹林區" };

type SheetTab = Exclude<WorkspaceTab, "map">;

/** 三張表：畫面上顯示 PDF；下載可選 PDF 或 xlsx。目前都是空白官方範本。 */
const SHEETS: Record<SheetTab, { pdf: string; xlsx: string; filename: string }> = {
  table3: { pdf: "/templates/table3.pdf", xlsx: "/templates/table3.xlsx", filename: "表3地價區段勘查表" },
  table4: { pdf: "/templates/table4.pdf", xlsx: "/templates/table4.xlsx", filename: "表4比較法調查估價表" },
  table5: { pdf: "/templates/table5.pdf", xlsx: "/templates/table5.xlsx", filename: "表5影響地價區域因素分析明細表(住宅用地)" },
};
const TEMPLATE_DOWNLOADS: Record<SheetTab, { href: string; filename: string }> = {
  table3: { href: SHEETS.table3.xlsx, filename: `${SHEETS.table3.filename}.xlsx` },
  table4: { href: SHEETS.table4.xlsx, filename: `${SHEETS.table4.filename}.xlsx` },
  table5: { href: SHEETS.table5.xlsx, filename: `${SHEETS.table5.filename}.xlsx` },
};

type Latest = { args: CaseInput; result: Table4Result };

type Props = {
  input: CaseInput;
  latest?: Latest;
  chatCollapsed: boolean;
  onToggleChat: () => void;
};

type TabMeta = (typeof WORKSPACE_TABS)[number];

const TabIcon: FC<{ id: WorkspaceTab; className?: string }> = ({ id, className }) =>
  id === "map" ? <MapIcon aria-hidden className={className} /> : <FileSpreadsheetIcon aria-hidden className={className} />;

/**
 * 右側工作區，仿 Codex 的瀏覽器面板：
 * 分頁列 → 網址列 → 文件內容。關閉後回到全寬聊天。
 */
export const Workspace: FC<Props> = ({ input, latest, chatCollapsed, onToggleChat }) => {
  const ws = useWorkspace();
  const history = useTabHistory();
  // ⟳ 直接把面板重新掛載（地圖會重建）。
  const [reloadKey, setReloadKey] = useState(0);
  const reload = () => setReloadKey((k) => k + 1);

  // ⌘1–⌘4 切換面板，Esc 關閉工作區、回到對話。
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey && !e.shiftKey && !e.altKey && e.key >= "1" && e.key <= "4") {
        e.preventDefault();
        ws.open(WORKSPACE_TABS[Number(e.key) - 1].id);
      } else if (e.key === "Escape" && ws.tab) {
        ws.close();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ws]);

  return (
    <section aria-label="工作區" className="relative flex h-full min-w-0 flex-col bg-background">
      <TabStrip chatCollapsed={chatCollapsed} onToggleChat={onToggleChat} />
      <NavRow history={history} onReload={reload} />

      {/* 內容貼邊：地圖與 PDF 都吃滿剩下的高度，自己管捲動。 */}
      <div className="relative min-h-0 flex-1 overflow-hidden">
        {ws.tab === null ? null : ws.tab === "map" ? (
          <MapPanel key={reloadKey} latest={latest} />
        ) : (
          <PdfViewer
            key={`${ws.tab}-${reloadKey}`}
            url={SHEETS[ws.tab].pdf}
            caption={`${WORKSPACE_TABS.find((t) => t.id === ws.tab)!.label}・空白範本${input.subject.parcel ? `・${input.subject.parcel}` : ""}`}
            className="h-full"
          />
        )}
      </div>
    </section>
  );
};

/* ---------- 分頁列 ---------- */

/**
 * 28px 命中區、16px 圖示的灰色圖示鈕；分頁列與網址列共用。
 * inactive＝長得像鈕但目前沒功能：灰一半、不吃焦點、滑過看得到 title（disabled 會吃掉 pointer events）。
 */
const IconButton: FC<ComponentProps<"button"> & { label: string; inactive?: boolean }> = ({
  label,
  inactive,
  className,
  children,
  ...rest
}) => (
  <button
    type="button"
    aria-label={label}
    title={label}
    aria-disabled={inactive || undefined}
    tabIndex={inactive ? -1 : undefined}
    className={cn(
      "inline-flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors",
      "focus-visible:ring-2 focus-visible:ring-ring/60 focus-visible:outline-none disabled:opacity-40",
      inactive ? "cursor-default text-muted-foreground/50" : "enabled:hover:bg-accent/70 enabled:hover:text-foreground",
      className,
    )}
    {...rest}
  >
    {children}
  </button>
);

const TabStrip: FC<{ chatCollapsed: boolean; onToggleChat: () => void }> = ({ chatCollapsed, onToggleChat }) => {
  const ws = useWorkspace();
  return (
    <div className="flex h-12 shrink-0 items-center gap-1.5 px-2">
      {/* 收合／顯示對話一定放最前面，對話收起來後才有地方把它叫回來。 */}
      <IconButton label={chatCollapsed ? "顯示對話" : "收合對話"} onClick={onToggleChat}>
        <PanelLeftIcon className="size-4" />
      </IconButton>

      <div
        role="tablist"
        aria-label="面板"
        className="flex min-w-0 items-center gap-1.5 overflow-x-auto [scrollbar-width:none]"
      >
        {WORKSPACE_TABS.map((t) => (
          <Tab key={t.id} tab={t} active={ws.tab === t.id} />
        ))}
      </div>

    </div>
  );
};

/**
 * 一個分頁：整塊可點（開面板），右邊的 × 只在 hover／作用中顯示。
 * 分頁是固定的，所以 × 只有作用中那個真的能按（回到對話）；其餘的只是視覺。
 */
const Tab: FC<{ tab: TabMeta; active: boolean }> = ({ tab, active }) => {
  const ws = useWorkspace();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = ref.current;
    if (!active || !node?.parentElement) return;
    const container = node.parentElement;
    const keepVisible = () => {
      if (!container.clientWidth) return;
      const bounds = container.getBoundingClientRect();
      const tabBounds = node.getBoundingClientRect();
      if (tabBounds.left < bounds.left) container.scrollLeft += tabBounds.left - bounds.left;
      else if (tabBounds.right > bounds.right) container.scrollLeft += tabBounds.right - bounds.right;
    };
    const observer = new ResizeObserver(keepVisible);
    observer.observe(container);
    keepVisible();
    return () => observer.disconnect();
  }, [active]);
  const label = `${tab.label}（${tab.shortcut}）`;
  return (
    <div
      ref={ref}
      className={cn(
        "group relative flex h-8 shrink-0 items-center gap-2 rounded-[10px] px-3 text-sm transition-colors",
        active ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
      )}
    >
      <button
        type="button"
        role="tab"
        aria-selected={active}
        aria-label={label}
        title={label}
        onClick={() => ws.open(tab.id)}
        className="absolute inset-0 rounded-[10px] focus-visible:ring-2 focus-visible:ring-ring/60 focus-visible:outline-none"
      />
      <TabIcon id={tab.id} className="pointer-events-none relative size-4" />
      <span className="pointer-events-none relative">{tab.short}</span>
      {active ? (
        <button
          type="button"
          onClick={ws.close}
          aria-label="關閉面板（Esc）"
          title="關閉面板（Esc）"
          className="relative z-10 inline-flex size-4 items-center justify-center rounded text-muted-foreground hover:text-foreground"
        >
          <XIcon className="size-3.5" />
        </button>
      ) : (
        <XIcon
          aria-hidden
          className="pointer-events-none relative size-3.5 opacity-0 transition-opacity group-hover:opacity-100"
        />
      )}
    </div>
  );
};

/* ---------- 網址列 ---------- */

type TabHistory = { canBack: boolean; canForward: boolean; back: () => void; forward: () => void };

/** 像瀏覽器那樣記住開過的面板（對話算 null），讓 ← → 有地方可走。 */
function useTabHistory(): TabHistory {
  const ws = useWorkspace();
  const [hist, setHist] = useState<{ entries: (WorkspaceTab | null)[]; index: number }>({
    entries: [null],
    index: 0,
  });

  // 面板換了就推一筆。render 期間跟著外部狀態調整自己的 state，是 React 建議的寫法；
  // ← → 造成的切換會在同一個事件裡連 index 一起改，這裡就不會重複推。
  if (hist.entries[hist.index] !== ws.tab) {
    const entries = [...hist.entries.slice(0, hist.index + 1), ws.tab];
    setHist({ entries, index: entries.length - 1 });
  }

  const go = (delta: number) => {
    const index = hist.index + delta;
    if (index < 0 || index >= hist.entries.length) return;
    setHist({ entries: hist.entries, index });
    const target = hist.entries[index];
    if (target === null) ws.close();
    else ws.open(target);
  };

  return {
    canBack: hist.index > 0,
    canForward: hist.index < hist.entries.length - 1,
    back: () => go(-1),
    forward: () => go(1),
  };
}

const NavRow: FC<{ history: TabHistory; onReload: () => void }> = ({ history, onReload }) => {
  const ws = useWorkspace();
  const meta = WORKSPACE_TABS.find((t) => t.id === ws.tab);
  return (
    // 三欄 grid、兩側等寬，標題才會像網址一樣真的置中。
    <div className="grid h-11 shrink-0 grid-cols-[1fr_auto_1fr] items-center px-3">
      <div className="flex items-center gap-1">
        <IconButton label="上一頁" disabled={!history.canBack} onClick={history.back}>
          <ArrowLeftIcon className="size-4" />
        </IconButton>
        <IconButton label="下一頁" disabled={!history.canForward} onClick={history.forward}>
          <ArrowRightIcon className="size-4" />
        </IconButton>
        <IconButton label="重新載入" disabled={!ws.tab} onClick={onReload}>
          <RotateCwIcon className="size-4" />
        </IconButton>
      </div>
      <div
        aria-live="polite"
        className={cn("min-w-0 truncate px-3 text-center text-sm", meta ? "text-foreground" : "text-muted-foreground")}
      >
        {meta ? meta.label : "尚未開啟面板"}
      </div>
      <div className="flex items-center justify-end gap-1">
        <NavMenu onReload={onReload} />
      </div>
    </div>
  );
};

const menuItemClass =
  "flex h-9 w-full items-center gap-2.5 rounded-lg px-2.5 text-sm text-foreground hover:bg-accent focus-visible:bg-accent focus-visible:outline-none";

/** ⋮ 選單：下載範本、重新載入、回到對話。 */
const NavMenu: FC<{ onReload: () => void }> = ({ onReload }) => {
  const ws = useWorkspace();
  // 記「為哪個面板開的」：面板一換，open 自然變 false，不用 effect 去關。
  const [openFor, setOpenFor] = useState<WorkspaceTab | null>(null);
  const open = openFor !== null && openFor === ws.tab;
  const setOpen = (next: boolean) => setOpenFor(next ? ws.tab : null);
  const ref = useRef<HTMLDivElement>(null);

  // 點到外面就關。
  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpenFor(null);
    };
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, [open]);

  const tab = ws.tab;
  return (
    <div
      ref={ref}
      className="relative"
      onKeyDown={(e) => {
        // 選單開著時 Esc 只關選單，不要連面板一起關。
        if (e.key === "Escape" && open) {
          e.stopPropagation();
          setOpen(false);
        }
      }}
    >
      <IconButton
        label="更多"
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={!tab}
        onClick={() => setOpen(!open)}
      >
        <EllipsisVerticalIcon className="size-4" />
      </IconButton>
      {open && tab && (
        <div
          role="menu"
          className="absolute end-0 top-full z-20 mt-1 min-w-48 rounded-xl border border-border bg-card p-1 shadow-lg shadow-black/40"
        >
          {tab !== "map" && (
            <>
              <a
                role="menuitem"
                href={SHEETS[tab].pdf}
                download={`${SHEETS[tab].filename}.pdf`}
                onClick={() => setOpen(false)}
                className={menuItemClass}
              >
                <FileTextIcon className="size-4 text-muted-foreground" />
                下載 PDF
              </a>
              <a
                role="menuitem"
                href={TEMPLATE_DOWNLOADS[tab].href}
                download={TEMPLATE_DOWNLOADS[tab].filename}
                onClick={() => setOpen(false)}
                className={menuItemClass}
              >
                <DownloadIcon className="size-4 text-muted-foreground" />
                下載 Excel
              </a>
            </>
          )}
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onReload();
            }}
            className={menuItemClass}
          >
            <RotateCwIcon className="size-4 text-muted-foreground" />
            重新載入
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              ws.close();
            }}
            className={menuItemClass}
          >
            <XIcon className="size-4 text-muted-foreground" />
            <span className="flex-1 text-start">關閉工作區，回到對話</span>
            <Kbd>Esc</Kbd>
          </button>
        </div>
      )}
    </div>
  );
};

const Kbd: FC<{ children: ReactNode }> = ({ children }) => (
  <kbd className="rounded-md bg-secondary px-2 py-0.5 font-sans text-xs text-[#b0b0b0]">{children}</kbd>
);

/* ---------- 內容 ---------- */

/** 地圖貼邊填滿整個內容區；有結果就標比準地與比較標的。 */
const MapPanel: FC<{ latest?: Latest }> = ({ latest }) => {
  const map = latest?.result.map;
  return (
    <div className="absolute inset-0">
      <CaseMap
        center={map?.center ?? DEFAULT_CENTER}
        subject={map?.subject}
        comparables={map?.comparables ?? []}
        className="h-full w-full rounded-none border-0"
      />
      {!map && (
        <div className="pointer-events-none absolute top-3 left-1/2 -translate-x-1/2 rounded-full bg-background/85 px-3 py-1 text-xs text-muted-foreground backdrop-blur">
          資料齊全後會標出比準地與 3 個比較標的
        </div>
      )}
    </div>
  );
};
