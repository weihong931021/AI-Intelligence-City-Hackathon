import type { PDFDocumentProxy } from "pdfjs-dist";
import { type FC, type ReactNode, useEffect, useRef, useState } from "react";

import { ZoomToolbar } from "@/components/workspace/ZoomToolbar";
import { useDocumentZoom } from "@/hooks/use-document-zoom";
import { loadPdfJs, pdfDocumentOptions } from "@/lib/pdf";
import { cn } from "@/lib/utils";

type Props = {
  url: string;
  caption?: ReactNode;
  className?: string;
};

type PageInfo = { index: number; width: number; height: number };

/**
 * 用 pdf.js 把 PDF 每一頁畫到 canvas，縮放時以新比例重畫（不糊）。
 * 預設符合寬度；雙指平移／捏合、快捷鍵與底部工具列共用同一組縮放狀態。
 */
export const PdfViewer: FC<Props> = ({ url, caption, className }) => {
  const docRef = useRef<PDFDocumentProxy | null>(null);
  const [pages, setPages] = useState<PageInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const pageWidth = pages.length ? Math.max(...pages.map((page) => page.width)) : 842;
  const { viewportRef, zoom, fitted, setManual, fit } = useDocumentZoom(pageWidth);

  // 載入文件與每頁尺寸
  useEffect(() => {
    let cancelled = false;
    setPages([]);
    setError(null);
    let task: ReturnType<typeof import("pdfjs-dist").getDocument> | undefined;
    loadPdfJs().then((pdfjs) => {
      if (cancelled) return;
      task = pdfjs.getDocument({ ...pdfDocumentOptions, url });
      return task.promise;
    })
      .then(async (doc) => {
        if (cancelled || !doc) return;
        docRef.current = doc;
        const infos: PageInfo[] = [];
        for (let i = 1; i <= doc.numPages; i++) {
          const page = await doc.getPage(i);
          const v = page.getViewport({ scale: 1 });
          infos.push({ index: i, width: v.width, height: v.height });
        }
        if (!cancelled) setPages(infos);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
      void task?.destroy();
      docRef.current = null;
    };
  }, [url]);

  return (
    <div className={cn("flex h-full min-h-0 flex-col", className)}>
      <div
        ref={viewportRef}
        tabIndex={0}
        aria-label="PDF 檢視，雙指滑動移動、捏合縮放，⌘= 放大、⌘- 縮小、⌘0 符合寬度"
        className="relative min-h-0 flex-1 overflow-auto overscroll-contain bg-[#0b0b0b] outline-none [overflow-anchor:none] [scrollbar-gutter:stable] focus-visible:ring-1 focus-visible:ring-ring/50"
      >
        {error && (
          <div className="flex h-full items-center justify-center px-6 text-center text-sm text-muted-foreground">
            PDF 載入失敗：{error}
          </div>
        )}
        {!error && pages.length === 0 && (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">載入中…</div>
        )}
        <div className="flex min-h-full w-max min-w-full flex-col items-center gap-6 px-6 py-6">
          {pages.map((p) => (
            <PdfPage key={p.index} docRef={docRef} info={p} zoom={zoom} />
          ))}
        </div>
      </div>
      <ZoomToolbar
        zoom={zoom}
        fitted={fitted}
        onZoom={setManual}
        onFit={fit}
        caption={
          <span>
            {caption}
            {pages.length > 0 && <span className="ms-2 text-muted-foreground/70">共 {pages.length} 頁</span>}
          </span>
        }
      />
    </div>
  );
};

const PdfPage: FC<{ docRef: React.RefObject<PDFDocumentProxy | null>; info: PageInfo; zoom: number }> = ({
  docRef,
  info,
  zoom,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const doc = docRef.current;
    const canvas = canvasRef.current;
    if (!doc || !canvas) return;
    let cancelled = false;
    let renderTask: ReturnType<Awaited<ReturnType<PDFDocumentProxy["getPage"]>>["render"]> | null = null;
    const dpr = window.devicePixelRatio || 1;
    const timer = setTimeout(async () => {
      const page = await doc.getPage(info.index);
      if (cancelled) return;
      const viewport = page.getViewport({ scale: zoom * dpr });
      canvas.width = Math.floor(viewport.width);
      canvas.height = Math.floor(viewport.height);
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      renderTask = page.render({ canvasContext: ctx, viewport, canvas });
      try {
        await renderTask.promise;
      } catch {
        /* 被新的縮放取消 */
      }
    }, 60); // 拖滑桿時合併重畫
    return () => {
      cancelled = true;
      clearTimeout(timer);
      renderTask?.cancel();
    };
  }, [docRef, info.index, zoom]);

  return (
    <canvas
      ref={canvasRef}
      data-zoom-page
      style={{ width: info.width * zoom, height: info.height * zoom }}
      className="shrink-0 rounded-[2px] bg-white shadow-[0_12px_40px_rgba(0,0,0,0.55)]"
      aria-label={`第 ${info.index} 頁`}
    />
  );
};
