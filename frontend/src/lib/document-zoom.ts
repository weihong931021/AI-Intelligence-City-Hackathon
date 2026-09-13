export const ZOOM_MIN = 0.25;
export const ZOOM_MAX = 3;
const STEPS = [0.25, 0.33, 0.5, 0.67, 0.75, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3];

export const clampZoom = (zoom: number) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, zoom));
export const zoomStepOut = (zoom: number) => [...STEPS].reverse().find((step) => step < zoom - 0.001) ?? ZOOM_MIN;
export const zoomStepIn = (zoom: number) => STEPS.find((step) => step > zoom + 0.001) ?? ZOOM_MAX;

export type Point = { x: number; y: number };
type PageBounds = { left: number; top: number; width: number; height: number };

/** 記住紙張上的相對位置，不把固定頁距、留白一起放大。 */
export function pagePointAt(point: Point, bounds: PageBounds): Point {
  return { x: (point.x - bounds.left) / bounds.width, y: (point.y - bounds.top) / bounds.height };
}

export function scrollForPagePoint(scroll: Point, pagePoint: Point, bounds: PageBounds, target: Point): Point {
  return {
    x: scroll.x + bounds.left + pagePoint.x * bounds.width - target.x,
    y: scroll.y + bounds.top + pagePoint.y * bounds.height - target.y,
  };
}

/** Chromium / Firefox 將觸控板捏合送成 ctrl + wheel；一般 wheel 仍交由瀏覽器捲動。 */
export function getWheelZoom(zoom: number, deltaY: number, deltaMode: number, viewportHeight: number): number {
  if (!Number.isFinite(deltaY)) return zoom;
  const pixels = deltaY * (deltaMode === 1 ? 16 : deltaMode === 2 ? viewportHeight : 1);
  return clampZoom(zoom * Math.exp(-pixels * 0.01));
}

/** 文件區內的 ⌘ / Ctrl 加減與符合寬度快捷鍵。 */
export function handleZoomKey(e: KeyboardEvent, zoom: number, onZoom: (zoom: number) => void, onFit: () => void) {
  if (!e.metaKey && !e.ctrlKey) return;
  if (e.key === "=" || e.key === "+") {
    e.preventDefault();
    onZoom(zoomStepIn(zoom));
  } else if (e.key === "-") {
    e.preventDefault();
    onZoom(zoomStepOut(zoom));
  } else if (e.key === "0") {
    e.preventDefault();
    onFit();
  }
}
