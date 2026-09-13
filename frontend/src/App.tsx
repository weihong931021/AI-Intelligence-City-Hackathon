import { AssistantRuntimeProvider, useAuiEvent, useAuiState, useLocalRuntime } from "@assistant-ui/react";
import { type FC, useCallback, useEffect, useMemo, useState } from "react";
import { flushSync } from "react-dom";

import { caseAgent } from "@/agent/backend";
import { documentAttachmentAdapter } from "@/agent/document-attachments";
import { collectCase, findLatestTable4 } from "@/agent/tools";
import { Thread } from "@/components/assistant-ui/thread";
import { MissingFieldsToolUI } from "@/components/tools/MissingFieldsCard";
import { DocumentRecognitionToolUI } from "@/components/tools/DocumentRecognitionCard";
import { Table4ToolUI } from "@/components/tools/Table4Card";
import { Workspace } from "@/components/workspace/Workspace";
import { WorkspaceContext, type WorkspaceTab } from "@/components/workspace/context";
import { useSplitWidth } from "@/hooks/use-split-width";
import { cn } from "@/lib/utils";

/** 有 View Transitions 就用它做「聊天縮到左欄」的轉場，沒有就直接切。 */
function withViewTransition(update: () => void) {
  const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown };
  if (typeof doc.startViewTransition === "function") {
    doc.startViewTransition(() => flushSync(update));
  } else {
    update();
  }
}

const Shell: FC = () => {
  const messages = useAuiState((s) => s.thread.messages);
  // 只有開啟文件／預覽才分欄，對話與補資料維持全寬。
  const [split, setSplit] = useState(false);
  const [chatCollapsed, setChatCollapsed] = useState(false);
  const [tab, setTab] = useState<WorkspaceTab | null>(null);
  const wantsSplit = tab !== null;

  useEffect(() => {
    if (split === wantsSplit) return;
    withViewTransition(() => setSplit(wantsSplit));
  }, [wantsSplit, split]);

  useAuiEvent("threads.selectionChanged", () => {
    setTab(null);
    setChatCollapsed(false);
  });

  const input = useMemo(() => collectCase(messages), [messages]);
  const latest = useMemo(() => findLatestTable4(messages), [messages]);
  const latestDocumentId = latest?.id;

  // 只在新文件完成時跳轉；關閉後的一般訊息不會重開同一份文件。
  useEffect(() => {
    if (!latestDocumentId) return;
    setTab("table4");
    setChatCollapsed(window.matchMedia("(max-width: 767px)").matches);
  }, [latestDocumentId]);

  const workspaceApi = useMemo(
    () => ({
      tab,
      open: (t: WorkspaceTab) => {
        setTab(t);
        if (window.matchMedia("(max-width: 767px)").matches) setChatCollapsed(true);
      },
      close: () => { setTab(null); setChatCollapsed(false); },
    }),
    [tab],
  );
  const toggleChat = useCallback(() => withViewTransition(() => setChatCollapsed((c) => !c)), []);
  const splitter = useSplitWidth();

  const title = input.subject.parcel ? `表4 比較法 ${input.subject.parcel}` : "表4 比較法調查估價表";

  return (
    <WorkspaceContext.Provider value={workspaceApi}>
      <Table4ToolUI />
      <MissingFieldsToolUI />
      <DocumentRecognitionToolUI />
      <div
        style={{ ["--chat-w" as string]: `${splitter.width}px` }}
        className={cn(
          "relative grid h-full min-h-0",
          splitter.dragging && "cursor-col-resize select-none",
          // 手機寬度一次只看一欄：收合對話就切到工作區。
          !split && "grid-cols-[1fr_0fr]",
          // 分欄：左聊天寬度可拖（記在 localStorage）、右工作區吃剩下的。
          split && !chatCollapsed && "grid-cols-[1fr_0fr] md:grid-cols-[var(--chat-w)_1fr]",
          split && chatCollapsed && "grid-cols-[0fr_1fr]",
        )}
      >
        <div
          style={{ viewTransitionName: "chat-pane" }}
          className={cn(
            "min-h-0 min-w-0 overflow-hidden",
            split && !chatCollapsed && "border-r border-divider",
          )}
        >
          <Thread split={split} title={title} onCollapse={split ? toggleChat : undefined} />
        </div>
        {/* 分隔線放在 grid 外層，才不會被聊天欄的 overflow-hidden 切掉。 */}
        {split && !chatCollapsed && (
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="拖曳調整對話欄寬度，雙擊還原"
            title="拖曳調整寬度，雙擊還原"
            onPointerDown={splitter.onPointerDown}
            onDoubleClick={splitter.reset}
            style={{ left: "calc(var(--chat-w) - 4px)" }}
            className={cn(
              "absolute inset-y-0 z-30 hidden w-2 cursor-col-resize md:block",
              "after:absolute after:inset-y-0 after:left-1/2 after:w-px after:-translate-x-1/2 after:bg-transparent after:transition-colors hover:after:bg-muted-foreground/50",
              splitter.dragging && "after:bg-muted-foreground/70",
            )}
          />
        )}
        <div style={{ viewTransitionName: "workspace" }} className="min-h-0 min-w-0 overflow-hidden">
          {split && tab !== null && <Workspace input={input} latest={latest} chatCollapsed={chatCollapsed} onToggleChat={toggleChat} />}
        </div>
      </div>
    </WorkspaceContext.Provider>
  );
};

export default function App() {
  const runtime = useLocalRuntime(caseAgent, { adapters: { attachments: documentAttachmentAdapter } });
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <Shell />
    </AssistantRuntimeProvider>
  );
}
