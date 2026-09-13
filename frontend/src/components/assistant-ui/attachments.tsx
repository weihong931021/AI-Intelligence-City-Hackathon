import { AttachmentPrimitive, ComposerPrimitive, MessagePrimitive, useAuiState } from "@assistant-ui/react";
import { FileSpreadsheetIcon, FileTextIcon, LoaderCircleIcon, XIcon } from "lucide-react";

function AttachmentChip({ removable = false }: { removable?: boolean }) {
  const attachment = useAuiState((s) => s.attachment);
  const error = attachment.status.type === "incomplete" ? attachment.status.message : null;
  const loading = attachment.status.type === "running";
  const Icon = /\.pdf$/i.test(attachment.name) ? FileTextIcon : FileSpreadsheetIcon;
  return (
    <AttachmentPrimitive.Root className="flex max-w-full items-center gap-2 rounded-xl bg-background/50 p-2.5 text-[13px]">
      {loading ? <LoaderCircleIcon className="size-4 shrink-0 animate-spin text-muted-foreground" /> : <Icon className="size-4 shrink-0 text-muted-foreground" />}
      <div className="min-w-0">
        <p className="truncate" title={attachment.name}>{attachment.name}</p>
        {removable && <p role={error ? "alert" : "status"} className={`max-w-72 text-xs ${error ? "text-red-300" : "text-muted-foreground"}`}>{error ?? (loading ? "正在準備文件…" : "已就緒，送出後自動辨識")}</p>}
      </div>
      {removable && <AttachmentPrimitive.Remove asChild><button type="button" aria-label={`移除 ${attachment.name}`} className="ml-1 rounded-full p-1 text-muted-foreground hover:bg-accent hover:text-foreground"><XIcon className="size-3.5" /></button></AttachmentPrimitive.Remove>}
    </AttachmentPrimitive.Root>
  );
}

export function ComposerAttachments() {
  const count = useAuiState((s) => s.composer.attachments.length);
  if (!count) return null;
  return (
    <div className="-mb-4 flex flex-col gap-2 px-1.5">
      <div className="flex max-h-40 flex-wrap gap-2 overflow-y-auto"><ComposerPrimitive.Attachments>{() => <AttachmentChip removable />}</ComposerPrimitive.Attachments></div>
      <p className="text-xs text-muted-foreground">送出後自動辨識文件，帶入案件欄位與來源。</p>
    </div>
  );
}

export function MessageAttachments() {
  return <div className="flex flex-col gap-2 empty:hidden"><MessagePrimitive.Attachments>{() => <AttachmentChip />}</MessagePrimitive.Attachments></div>;
}
