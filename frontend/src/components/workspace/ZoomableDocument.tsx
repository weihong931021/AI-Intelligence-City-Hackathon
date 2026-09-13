import { type FC, type ReactNode, useLayoutEffect, useRef, useState } from "react";

import { ZoomToolbar } from "@/components/workspace/ZoomToolbar";
import { useDocumentZoom } from "@/hooks/use-document-zoom";
import { cn } from "@/lib/utils";

type Props = {
  /** 文件本身的自然寬度（px）。表4 是橫式 A4，約 1123px。 */
  pageWidth: number;
  /** 自然高度（px）；不給就由內容決定。 */
  pageHeight?: number;
  caption?: ReactNode;
  className?: string;
  children: ReactNode;
};

/**
 * 深色畫布上的一張「紙」（HTML 內容）：雙指移動／捏合、滑桿與鍵盤縮放，預設符合寬度。
 * 縮放用 transform，不重排內容。
 */
export const ZoomableDocument: FC<Props> = ({ pageWidth, pageHeight, caption, className, children }) => {
  const { viewportRef, zoom, fitted, setManual, fit } = useDocumentZoom(pageWidth);
  const contentRef = useRef<HTMLDivElement>(null);
  const [contentHeight, setContentHeight] = useState(0);

  useLayoutEffect(() => {
    const content = contentRef.current;
    if (!content || pageHeight !== undefined) return;
    const measure = () => setContentHeight(content.offsetHeight);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(content);
    return () => observer.disconnect();
  }, [pageHeight]);

  return (
    <div className={cn("flex h-full min-h-0 flex-col", className)}>
      <div
        ref={viewportRef}
        tabIndex={0}
        aria-label="文件檢視，雙指滑動移動、捏合縮放，⌘= 放大、⌘- 縮小、⌘0 符合寬度"
        className="relative min-h-0 flex-1 overflow-auto overscroll-contain bg-[#0b0b0b] outline-none [overflow-anchor:none] [scrollbar-gutter:stable] focus-visible:ring-1 focus-visible:ring-ring/50"
      >
        <div className="flex min-h-full w-max min-w-full items-start justify-center px-6 py-6">
          <div style={{ width: pageWidth * zoom, height: (pageHeight ?? contentHeight) * zoom }} className="shrink-0">
            <div
              ref={contentRef}
              data-zoom-page
              style={{ width: pageWidth, transform: `scale(${zoom})`, transformOrigin: "top left" }}
              className="rounded-[2px] bg-white text-neutral-900 shadow-[0_12px_40px_rgba(0,0,0,0.55)]"
            >
              {children}
            </div>
          </div>
        </div>
      </div>
      <ZoomToolbar zoom={zoom} fitted={fitted} onZoom={setManual} onFit={fit} caption={caption} />
    </div>
  );
};
