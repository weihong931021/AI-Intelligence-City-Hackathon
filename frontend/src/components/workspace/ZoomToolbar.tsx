import { MinusIcon, PlusIcon } from "lucide-react";
import type { FC, ReactNode } from "react";

import { ZOOM_MIN, ZOOM_MAX, zoomStepIn, zoomStepOut } from "@/lib/document-zoom";
import { cn } from "@/lib/utils";

type Props = {
  zoom: number;
  fitted: boolean;
  onZoom: (z: number) => void;
  onFit: () => void;
  caption?: ReactNode;
};

/** 文件底部的縮放列：− 滑桿 + 百分比 符合寬度。 */
export const ZoomToolbar: FC<Props> = ({ zoom, fitted, onZoom, onFit, caption }) => (
  <div className="flex h-11 shrink-0 items-center gap-3 border-t border-border/60 px-3 text-xs text-muted-foreground">
    <div className="min-w-0 flex-1 truncate">{caption}</div>
    <button
      type="button"
      onClick={() => onZoom(zoomStepOut(zoom))}
      aria-label="縮小"
      className="rounded-md p-1 hover:bg-accent hover:text-foreground disabled:opacity-40"
      disabled={zoom <= ZOOM_MIN + 0.001}
    >
      <MinusIcon className="size-4" />
    </button>
    <input
      type="range"
      min={ZOOM_MIN}
      max={ZOOM_MAX}
      step={0.01}
      value={zoom}
      onChange={(e) => onZoom(Number(e.target.value))}
      aria-label="縮放"
      className="h-1 w-32 cursor-pointer accent-white"
    />
    <button
      type="button"
      onClick={() => onZoom(zoomStepIn(zoom))}
      aria-label="放大"
      className="rounded-md p-1 hover:bg-accent hover:text-foreground disabled:opacity-40"
      disabled={zoom >= ZOOM_MAX - 0.001}
    >
      <PlusIcon className="size-4" />
    </button>
    <span className="w-12 text-end tabular-nums text-foreground">{Math.round(zoom * 100)}%</span>
    <button
      type="button"
      onClick={onFit}
      className={cn("rounded-md px-2 py-1 hover:bg-accent hover:text-foreground", fitted && "text-foreground")}
    >
      符合寬度
    </button>
  </div>
);
