import type { Attachment, AttachmentAdapter, CompleteAttachment, PendingAttachment } from "@assistant-ui/react";
import { loadPdfJs, pdfDocumentOptions } from "../lib/pdf";
import type { DocumentPayload } from "./recognition";

export const MAX_DOCUMENT_BYTES = 10 * 1024 * 1024;
const MAX_TEXT_LENGTH = 80_000;
const MAX_PDF_PAGES = 50;
const ACCEPT = ".xlsx,.xls,.csv,.tsv,.pdf";

function checkText(text: string): string {
  if (text.length > MAX_TEXT_LENGTH) throw new Error("文件文字超過 80,000 字，請拆成較小的檔案後再匯入。");
  return text;
}

async function readSpreadsheet(file: File): Promise<string> {
  // 大型解析器按需載入，不影響第一次打開聊天畫面。
  const XLSX = await import("xlsx");
  const isText = /\.(csv|tsv)$/i.test(file.name);
  const book = XLSX.read(isText ? await file.text() : await file.arrayBuffer(), {
    type: isText ? "string" : "array",
    raw: isText,
    dense: true,
  });
  const sheets: string[] = [];
  let length = 0;
  const table = file.name.match(/表\s*([345])/)?.[1];
  const matching = table ? book.SheetNames.filter((name) => new RegExp(`表\\s*${table}(?:[^0-9]|$)`).test(name)) : [];
  // 官方母簿有二十多張空白表，先讀與檔名相符的工作表，避免混入其他表。
  const names = matching.length ? matching : book.SheetNames;
  for (const name of names) {
    const sheet = book.Sheets[name];
    const range = sheet["!ref"] ? XLSX.utils.decode_range(sheet["!ref"]) : null;
    if (!range) continue;
    if ((range.e.r - range.s.r + 1) * (range.e.c - range.s.c + 1) > 100_000) {
      throw new Error("表格範圍過大，請只保留需要的資料後再匯入。");
    }
    const rows = XLSX.utils.sheet_to_json<string[]>(sheet, { header: 1, raw: false, defval: "", blankrows: true });
    const body = rows.map((row, r) => row.flatMap((cell, c) => {
      if (cell === "") return [];
      const address = XLSX.utils.encode_cell({ r: range.s.r + r, c: range.s.c + c });
      return [`${address}=${JSON.stringify(String(cell))}`];
    }).join("\t")).filter(Boolean).join("\n").trim();
    if (!body) continue;
    const text = `工作表：${name}\n${body}`;
    length += text.length;
    if (length > MAX_TEXT_LENGTH) throw new Error("文件文字超過 80,000 字，請拆成較小的檔案後再匯入。");
    sheets.push(text);
  }
  if (!sheets.length) throw new Error("表格是空白的，請選擇有資料的檔案。");
  return checkText(sheets.join("\n\n"));
}

async function readPdf(file: File): Promise<DocumentPayload> {
  const pdfjs = await loadPdfJs();
  const task = pdfjs.getDocument({ ...pdfDocumentOptions, data: await file.arrayBuffer() });
  try {
    const doc = await task.promise;
    if (doc.numPages > MAX_PDF_PAGES) throw new Error("PDF 超過 50 頁，請拆成較小的檔案後再匯入。");
    const pages: string[] = [];
    const images: DocumentPayload["images"] = [];
    for (let n = 1; n <= doc.numPages; n++) {
      const page = await doc.getPage(n);
      const content = await page.getTextContent();
      const items = content.items.filter((item) => "str" in item);
      items.sort((a, b) => Math.abs(a.transform[5] - b.transform[5]) > 3 ? b.transform[5] - a.transform[5] : a.transform[4] - b.transform[4]);
      let lastY = NaN;
      const text = items.map((item) => {
        const prefix = Math.abs(item.transform[5] - lastY) > 3 ? "\n" : "\t";
        lastY = item.transform[5];
        return `${prefix}${item.str}`;
      }).join("").trim();
      if (text) pages.push(`第 ${n} 頁\n${text}`);
      checkText(pages.join("\n\n"));
      // 保留頁面影像，掃描 PDF 與圖文混合表格也能依實際版面辨識。
      const base = page.getViewport({ scale: 1 });
      const viewport = page.getViewport({ scale: 1800 / Math.max(base.width, base.height) });
      const canvas = document.createElement("canvas");
      canvas.width = Math.ceil(viewport.width);
      canvas.height = Math.ceil(viewport.height);
      await page.render({ canvas, viewport }).promise;
      images.push({ page: n, data: canvas.toDataURL("image/jpeg", 0.85).split(",")[1] });
      canvas.width = canvas.height = 0;
      page.cleanup();
    }
    return { name: file.name, text: pages.join("\n\n"), images };
  } catch (error) {
    if (error instanceof Error && error.name === "PasswordException") throw new Error("PDF 已加密，請先解除密碼再匯入。");
    throw error;
  } finally {
    await task.destroy();
  }
}

export async function extractDocumentText(file: File): Promise<string> {
  return (await prepareDocument(file)).text;
}

export async function prepareDocument(file: File): Promise<DocumentPayload> {
  if (!/\.(xlsx|xls|csv|tsv|pdf)$/i.test(file.name)) throw new Error("支援 Excel、CSV、TSV 與 PDF 檔案。");
  if (file.size > MAX_DOCUMENT_BYTES) throw new Error("每個檔案最多 10 MB，請縮小檔案後再匯入。");
  if (!file.size) throw new Error("檔案是空白的，請重新選擇。");
  return /\.pdf$/i.test(file.name) ? readPdf(file) : { name: file.name, text: await readSpreadsheet(file), images: [] };
}

export async function attachmentDocument(attachment: Attachment): Promise<DocumentPayload> {
  const data = attachment.content?.find((part) => part.type === "data" && part.name === "landlens-document");
  if (data?.type === "data") return data.data as DocumentPayload;
  // 相容上一版已送出的附件，重新產生時也可辨識。
  if (attachment.file) return prepareDocument(attachment.file);
  return { name: attachment.name, text: (attachment.content ?? []).filter((part) => part.type === "text").map((part) => part.text).join("\n"), images: [] };
}

export const documentAttachmentAdapter = {
  accept: ACCEPT,
  async *add({ file }: { file: File }): AsyncGenerator<PendingAttachment, void> {
    const base = { id: crypto.randomUUID(), type: "document", name: file.name, contentType: file.type, file };
    yield { ...base, status: { type: "running", reason: "uploading", progress: 0 } };
    try {
      const document = await prepareDocument(file);
      yield {
        ...base,
        content: [
          { type: "text", text: `附件 ${JSON.stringify(file.name)}\n${document.text || `PDF 共 ${document.images.length} 頁，送出後辨識頁面內容。`}\n附件結束` },
          { type: "data", name: "landlens-document", data: document },
        ],
        status: { type: "requires-action", reason: "composer-send" },
      };
    } catch (error) {
      yield { ...base, status: { type: "incomplete", reason: "error", message: error instanceof Error ? error.message : "文件讀取失敗，請確認檔案格式。" } };
    }
  },
  async send(attachment: PendingAttachment): Promise<CompleteAttachment> {
    if (attachment.status.type !== "requires-action" || !attachment.content?.length) {
      throw new Error("請等候文件讀取完成，或移除讀取失敗的附件。");
    }
    return { ...attachment, status: { type: "complete" }, content: attachment.content };
  },
  async remove() { /* 檔案僅存在這段對話記憶體，不需要刪除遠端檔案。 */ },
} satisfies AttachmentAdapter;
