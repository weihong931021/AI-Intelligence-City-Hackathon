import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { clampZoom, getWheelZoom, handleZoomKey, pagePointAt, scrollForPagePoint, type Point } from "@/lib/document-zoom";

type Anchor = { page: HTMLElement; pagePoint: Point; target: Point };
type SafariGestureEvent = Event & { scale: number; clientX: number; clientY: number };

function viewportCenter(viewport: HTMLElement): Point {
  const bounds = viewport.getBoundingClientRect();
  return { x: bounds.left + viewport.clientWidth / 2, y: bounds.top + viewport.clientHeight / 2 };
}

function captureAnchor(viewport: HTMLElement, target: Point): Anchor | null {
  let nearest: Anchor | null = null;
  let distance = Infinity;
  for (const page of viewport.querySelectorAll<HTMLElement>("[data-zoom-page]")) {
    const bounds = page.getBoundingClientRect();
    if (!bounds.width || !bounds.height) continue;
    const dx = Math.max(bounds.left - target.x, 0, target.x - bounds.right);
    const dy = Math.max(bounds.top - target.y, 0, target.y - bounds.bottom);
    const d = dx * dx + dy * dy;
    if (d < distance) {
      distance = d;
      nearest = { page, pagePoint: pagePointAt(target, bounds), target };
    }
  }
  return nearest;
}

function restoreAnchor(viewport: HTMLElement, anchor: Anchor | null) {
  if (!anchor || !viewport.contains(anchor.page)) return;
  const scroll = scrollForPagePoint(
    { x: viewport.scrollLeft, y: viewport.scrollTop },
    anchor.pagePoint, anchor.page.getBoundingClientRect(), anchor.target,
  );
  viewport.scrollLeft = scroll.x;
  viewport.scrollTop = scroll.y;
}

/** PDF 與 HTML 文件共用：原生雙指平移、以游標／手勢中心為準的捏合縮放。 */
export function useDocumentZoom(pageWidth: number) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState(1);
  const [fitted, setFitted] = useState(true);
  const zoomRef = useRef(1);
  const fittedRef = useRef(true);
  const pendingAnchor = useRef<Anchor | null>(null);

  const applyZoom = useCallback((value: number, anchor: Anchor | null) => {
    const viewport = viewportRef.current;
    if (!viewport || !Number.isFinite(value)) return;
    const next = clampZoom(value);
    fittedRef.current = false;
    setFitted(false);
    if (next === zoomRef.current) {
      restoreAnchor(viewport, anchor);
      return;
    }
    pendingAnchor.current = anchor;
    zoomRef.current = next;
    setZoom(next);
  }, []);

  const setManual = useCallback((value: number) => {
    const viewport = viewportRef.current;
    if (viewport) applyZoom(value, captureAnchor(viewport, viewportCenter(viewport)));
  }, [applyZoom]);

  const fit = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport || viewport.clientWidth <= 48) return;
    const next = clampZoom((viewport.clientWidth - 48) / pageWidth);
    pendingAnchor.current = null;
    zoomRef.current = next;
    fittedRef.current = true;
    setZoom(next);
    setFitted(true);
    viewport.scrollLeft = 0;
    viewport.scrollTop = 0;
  }, [pageWidth]);

  useLayoutEffect(() => { fit(); }, [fit]);

  // 更新頁面尺寸後、瀏覽器繪製前補償捲動，避免每次捏合都跳向固定原點。
  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    if (viewport) restoreAnchor(viewport, pendingAnchor.current);
    pendingAnchor.current = null;
  }, [zoom]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const observer = new ResizeObserver(() => { if (fittedRef.current) fit(); });
    observer.observe(viewport);
    return () => observer.disconnect();
  }, [fit]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    let pointer: Point | null = null;
    let gesture: { zoom: number; scale: number; anchor: Anchor | null } | null = null;

    const gesturePoint = (e: SafariGestureEvent): Point => {
      const bounds = viewport.getBoundingClientRect();
      if (Number.isFinite(e.clientX) && Number.isFinite(e.clientY)
        && e.clientX >= bounds.left && e.clientX <= bounds.right
        && e.clientY >= bounds.top && e.clientY <= bounds.bottom) {
        return { x: e.clientX, y: e.clientY };
      }
      return pointer ?? viewportCenter(viewport);
    };
    const onPointerMove = (e: PointerEvent) => { pointer = { x: e.clientX, y: e.clientY }; };
    const onPointerLeave = () => { pointer = null; };
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey) return; // 雙指平移與慣性捲動完全沿用瀏覽器。
      e.preventDefault();
      if (gesture) return; // Safari 同時送兩種事件時，只處理 gesture。
      const point = { x: e.clientX, y: e.clientY };
      applyZoom(getWheelZoom(zoomRef.current, e.deltaY, e.deltaMode, viewport.clientHeight), captureAnchor(viewport, point));
    };
    const onGestureStart = (event: Event) => {
      const e = event as SafariGestureEvent;
      e.preventDefault();
      gesture = {
        zoom: zoomRef.current,
        scale: Number.isFinite(e.scale) && e.scale > 0 ? e.scale : 1,
        anchor: captureAnchor(viewport, gesturePoint(e)),
      };
    };
    const onGestureChange = (event: Event) => {
      const e = event as SafariGestureEvent;
      if (!gesture) return;
      e.preventDefault();
      if (!Number.isFinite(e.scale) || e.scale <= 0) return;
      const anchor = gesture.anchor ? { ...gesture.anchor, target: gesturePoint(e) } : null;
      applyZoom(gesture.zoom * e.scale / gesture.scale, anchor);
    };
    const onGestureEnd = (e: Event) => {
      if (!gesture) return;
      e.preventDefault();
      gesture = null;
    };
    const onBlur = () => { gesture = null; };
    const onKey = (e: KeyboardEvent) => handleZoomKey(e, zoomRef.current, setManual, fit);

    viewport.addEventListener("wheel", onWheel, { passive: false });
    viewport.addEventListener("gesturestart", onGestureStart, { passive: false });
    viewport.addEventListener("gesturechange", onGestureChange, { passive: false });
    // 手勢在文件區外結束或視窗失焦，也要結束這次縮放，避免阻擋下一次 wheel。
    window.addEventListener("gestureend", onGestureEnd, { passive: false });
    window.addEventListener("blur", onBlur);
    viewport.addEventListener("pointermove", onPointerMove);
    viewport.addEventListener("pointerleave", onPointerLeave);
    viewport.addEventListener("keydown", onKey);
    return () => {
      viewport.removeEventListener("wheel", onWheel);
      viewport.removeEventListener("gesturestart", onGestureStart);
      viewport.removeEventListener("gesturechange", onGestureChange);
      window.removeEventListener("gestureend", onGestureEnd);
      window.removeEventListener("blur", onBlur);
      viewport.removeEventListener("pointermove", onPointerMove);
      viewport.removeEventListener("pointerleave", onPointerLeave);
      viewport.removeEventListener("keydown", onKey);
    };
  }, [applyZoom, fit, setManual]);

  return { viewportRef, zoom, fitted, setManual, fit };
}
