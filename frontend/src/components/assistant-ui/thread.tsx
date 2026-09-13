import {
  ActionBarPrimitive,
  AuiIf,
  ComposerPrimitive,
  ErrorPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAui,
  useAuiState,
} from "@assistant-ui/react";
import {
  ArrowDownIcon,
  ArrowUpIcon,
  ChartPieIcon,
  CheckIcon,
  CopyIcon,
  FolderIcon,
  MicIcon,
  PanelLeftIcon,
  PlusIcon,
  RefreshCwIcon,
  SquareIcon,
  SquarePenIcon,
  UploadIcon,
} from "lucide-react";
import { type FC, type MouseEvent, useCallback, useEffect, useRef, useState } from "react";

import { SAMPLE_CASE_TEXT } from "@/agent/sample";
import { ComposerAttachments, MessageAttachments } from "@/components/assistant-ui/attachments";
import { ContextChips, ModelInfoButton } from "@/components/assistant-ui/composer-controls";
import { MarkdownText } from "@/components/assistant-ui/markdown-text";
import { TooltipIconButton } from "@/components/assistant-ui/tooltip-icon-button";
import { Button } from "@/components/ui/button";
import { useWorkspace } from "@/components/workspace/context";
import { cn } from "@/lib/utils";

export type ThreadProps = {
  /** 是否正在右側檢視文件；一般對話維持全寬。 */
  split: boolean;
  title: string;
  onCollapse?: () => void;
};

/**
 * Codex 風格的聊天欄。
 * 空白時：置中的標題 + 情境列 + 輸入框；送出後：頂列在上、訊息串中間、輸入框貼底。
 */
export const Thread: FC<ThreadProps> = ({ split, title, onCollapse }) => {
  const hasMessages = useAuiState((s) => s.thread.messages.length > 0);
  const showConversation = hasMessages || split;
  return (
  <ThreadPrimitive.Root
    className="aui-root flex h-full min-w-0 flex-col bg-background"
    style={{
      ["--thread-max-width" as string]: split ? "100%" : "52.5rem",
      ["--composer-bg" as string]: "#232323",
      ["--composer-radius" as string]: "24px",
    }}
  >
    {showConversation && <ChatTopBar title={title} onCollapse={onCollapse} />}

    <ThreadPrimitive.Viewport
      turnAnchor="top"
      className="relative flex min-h-0 flex-1 flex-col overflow-x-hidden overflow-y-auto"
    >
      <div
        className={cn(
          "mx-auto flex w-full max-w-(--thread-max-width) flex-1 flex-col px-4",
          showConversation ? "pt-4" : "justify-center py-8 sm:py-12",
        )}
      >
        {!showConversation && <ThreadWelcome />}

        <div className="mb-6 flex flex-col gap-y-6 empty:hidden">
          <ThreadPrimitive.Messages>{() => <ThreadMessage />}</ThreadPrimitive.Messages>
        </div>

        <ThreadPrimitive.ViewportFooter
          className={cn("relative flex flex-col bg-background", showConversation && "sticky bottom-0 mt-auto pt-4 pb-4")}
        >
          <ThreadScrollToBottom />
          <ContextChips />
          <Composer />
        </ThreadPrimitive.ViewportFooter>
      </div>
    </ThreadPrimitive.Viewport>
  </ThreadPrimitive.Root>
  );
};

/* ---------- 左欄頂列 ---------- */

/** 左欄頂列：收合、新對話、案件名稱與分享。 */
const ChatTopBar: FC<{ title: string; onCollapse?: () => void }> = ({ title, onCollapse }) => {
  const aui = useAui();
  const workspace = useWorkspace();
  const newThread = () => {
    workspace.close();
    if (aui.thread().getState().messages.length === 0) void aui.composer().reset();
    void aui.threads().switchToNewThread();
  };
  return (
    <div className="flex h-12 shrink-0 items-center px-3">
      <div className="flex min-w-0 flex-1 items-center gap-0.5">
        {onCollapse && (
          <TooltipIconButton tooltip="收合對話" onClick={onCollapse}>
            <PanelLeftIcon />
          </TooltipIconButton>
        )}
        <TooltipIconButton tooltip="新對話" onClick={newThread}>
          <SquarePenIcon />
        </TooltipIconButton>
        <span aria-hidden="true" className="mx-1.5 h-4 w-px shrink-0 bg-border" />
        <FolderIcon className="ms-1 size-4 shrink-0 text-muted-foreground" />
        <span className="ms-1.5 truncate text-[13px] text-foreground">{title}</span>
      </div>
      <div className="ms-2 flex shrink-0 items-center gap-0.5">
        <ShareButton text={title} />
      </div>
    </div>
  );
};

/** 「分享」：把案件名稱複製到剪貼簿，1.5 秒內顯示「已複製」。 */
const ShareButton: FC<{ text: string }> = ({ text }) => {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      return; // 非安全環境或沒授權：剪貼簿不可用就不動
    }
    setCopied(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), 1500);
  }, [text]);

  return (
    <Button type="button" variant="chrome" size="pill" className="text-[13px]" onClick={copy} aria-live="polite" title="複製案件名稱">
      {copied ? <CheckIcon className="size-3.5" /> : <UploadIcon className="size-3.5" />}
      {copied ? "已複製" : "分享"}
    </Button>
  );
};

/* ---------- 訊息 ---------- */

const ThreadMessage: FC = () => {
  const role = useAuiState((s) => s.message.role);
  if (role === "user") return <UserMessage />;
  return <AssistantMessage />;
};

const ThreadScrollToBottom: FC = () => (
  <ThreadPrimitive.ScrollToBottom asChild>
    <TooltipIconButton
      tooltip="捲到最下面"
      variant="outline"
      size="icon"
      className="absolute -top-12 z-10 self-center rounded-full border-border bg-card text-muted-foreground shadow-md hover:bg-accent hover:text-foreground disabled:invisible"
    >
      <ArrowDownIcon />
    </TooltipIconButton>
  </ThreadPrimitive.ScrollToBottom>
);

const MessageError: FC = () => (
  <MessagePrimitive.Error>
    <ErrorPrimitive.Root className="mt-2 rounded-md border border-destructive bg-destructive/10 p-3 text-[13px] text-destructive">
      <ErrorPrimitive.Message className="line-clamp-2" />
    </ErrorPrimitive.Root>
  </MessagePrimitive.Error>
);

/** 助理訊息：純文字、沒有泡泡；最後一則下方有複製／重新產生。 */
const AssistantMessage: FC = () => (
  <MessagePrimitive.Root data-role="assistant" className="relative">
    <div className="text-sm leading-[22px] wrap-break-word text-foreground">
      <MessagePrimitive.Parts components={{ Text: MarkdownText }} />
      <MessageError />
    </div>
    <div className="flex min-h-7 items-center pt-2">
      <AssistantActionBar />
    </div>
  </MessagePrimitive.Root>
);

const AssistantActionBar: FC = () => (
  <ActionBarPrimitive.Root
    hideWhenRunning
    autohide="not-last"
    className="-ms-1.5 flex items-center gap-0.5 text-muted-foreground"
  >
    <ActionBarPrimitive.Copy asChild>
      <TooltipIconButton tooltip="複製">
        <AuiIf condition={(s) => s.message.isCopied}>
          <CheckIcon />
        </AuiIf>
        <AuiIf condition={(s) => !s.message.isCopied}>
          <CopyIcon />
        </AuiIf>
      </TooltipIconButton>
    </ActionBarPrimitive.Copy>
    <ActionBarPrimitive.Reload asChild>
      <TooltipIconButton tooltip="重新產生">
        <RefreshCwIcon />
      </TooltipIconButton>
    </ActionBarPrimitive.Reload>
  </ActionBarPrimitive.Root>
);

/** 使用者訊息：靠右的深灰泡泡。 */
const UserMessage: FC = () => (
  <MessagePrimitive.Root data-role="user" className="flex justify-end">
    <div className="flex max-w-[85%] flex-col gap-2 rounded-[18px] bg-muted px-3.5 py-2.5 text-sm leading-[22px] whitespace-pre-wrap wrap-break-word text-foreground">
      <MessageAttachments />
      <MessagePrimitive.Parts />
    </div>
  </MessagePrimitive.Root>
);

/* ---------- 空白畫面 ---------- */

const ThreadWelcome: FC = () => (
  <div className="mb-7 flex flex-col items-center px-2 text-center sm:mb-8">
    <h1 className="text-2xl font-normal tracking-tight text-foreground sm:text-[28px]">
      想在{" "}
      <span className="underline decoration-1 decoration-muted-foreground/60 underline-offset-[7px]">LandLens</span>{" "}
      裡查估什麼？
    </h1>
  </div>
);

/* ---------- 輸入框 ---------- */

/** 點到框內的空白處也把游標放進 textarea。 */
function focusComposerInput(e: MouseEvent<HTMLDivElement>) {
  if ((e.target as HTMLElement).closest("button, textarea, a, [role='button']")) return;
  e.currentTarget.querySelector("textarea")?.focus();
}

const Composer: FC = () => {
  const blocked = useAuiState((s) => s.composer.attachments.some((a) => a.status.type === "running" || a.status.type === "incomplete"));
  return (
  <ComposerPrimitive.Root className="relative @container flex w-full flex-col" onSubmit={(e) => { if (blocked) e.preventDefault(); }}>
    <div
      style={{ viewTransitionName: "composer" }}
      onClick={focusComposerInput}
      className={cn(
        "relative z-10 -mt-1.5 flex w-full cursor-text flex-col gap-7 rounded-(--composer-radius) bg-(--composer-bg) px-2 pt-4 pb-2",
      )}
    >
      <ComposerAttachments />
      <ComposerPrimitive.Input
        placeholder="想做什麼都可以"
        className="min-h-6 max-h-[min(12rem,35dvh)] w-full shrink-0 resize-none overflow-y-auto border-0 bg-transparent px-1.5 text-base leading-6 text-[#f5f5f5] shadow-none outline-none placeholder:font-normal placeholder:text-[#606060] focus:ring-0 sm:text-sm sm:leading-[22px]"
        rows={1}
        minRows={1}
        maxRows={8}
        submitMode={blocked ? "none" : "enter"}
        autoFocus
        enterKeyHint="send"
        aria-label="訊息輸入"
      />
      <ComposerAction attachmentsBlocked={blocked} />
    </div>
  </ComposerPrimitive.Root>
  );
};

const ComposerAction: FC<{ attachmentsBlocked: boolean }> = ({ attachmentsBlocked }) => {
  const aui = useAui();
  return (
    <div className="flex h-8 shrink-0 items-center justify-between gap-2">
      <div className="flex shrink-0 items-center gap-1">
        <ComposerPrimitive.AddAttachment multiple asChild>
        <TooltipIconButton
          tooltip="匯入 Excel／CSV／PDF（每檔最多 10 MB）"
          side="top"
          type="button"
          className="size-8 rounded-full text-[#f5f5f5]"
          aria-label="匯入表格或 PDF"
        >
          <PlusIcon className="size-5" />
        </TooltipIconButton>
        </ComposerPrimitive.AddAttachment>
        <Button
          type="button"
          variant="chrome"
          size="pill"
          className="h-8 gap-1.5 text-[13px] text-[#999]"
          title="載入資料齊全的範例"
          onClick={() => aui.composer().setText(SAMPLE_CASE_TEXT)}
        >
          <ChartPieIcon className="size-4" />
          載入範例
        </Button>
      </div>
      <div className="flex min-w-0 items-center gap-3">
        <ModelInfoButton />
        <AuiIf condition={(s) => s.thread.capabilities.dictation}>
          <ComposerPrimitive.Dictate asChild>
            <TooltipIconButton tooltip="語音輸入" side="top" type="button" className="size-8 rounded-full text-[#f5f5f5]">
              <MicIcon className="size-5" />
            </TooltipIconButton>
          </ComposerPrimitive.Dictate>
        </AuiIf>
        <AuiIf condition={(s) => !s.thread.isRunning}>
          <ComposerPrimitive.Send asChild>
            <TooltipIconButton
              tooltip="送出"
              side="top"
              type="button"
              variant="default"
              size="icon"
              className="size-8 rounded-full bg-[#fafafa] text-[#232323] hover:bg-white disabled:opacity-100"
              aria-label="送出訊息"
              disabled={attachmentsBlocked}
            >
              <ArrowUpIcon className="size-[18px]" strokeWidth={2.25} />
            </TooltipIconButton>
          </ComposerPrimitive.Send>
        </AuiIf>
        <AuiIf condition={(s) => s.thread.isRunning}>
          <ComposerPrimitive.Cancel asChild>
            <Button type="button" variant="default" size="icon" className="size-8 rounded-full bg-[#fafafa] text-[#232323]" aria-label="停止">
              <SquareIcon className="size-3 fill-current" />
            </Button>
          </ComposerPrimitive.Cancel>
        </AuiIf>
      </div>
    </div>
  );
};
