import { type PointerEvent as ReactPointerEvent, useCallback, useEffect, useRef, useState } from "react";

const KEY = "landlens.chatWidth";
export const MIN_CHAT_WIDTH = 320;
export const DEFAULT_CHAT_WIDTH = 480;

function clamp(px: number) {
  const max = Math.max(MIN_CHAT_WIDTH, Math.floor(window.innerWidth * 0.6));
  return Math.min(max, Math.max(MIN_CHAT_WIDTH, Math.round(px)));
}

function readStored(): number {
  try {
    const v = Number(localStorage.getItem(KEY));
    if (Number.isFinite(v) && v >= MIN_CHAT_WIDTH) return v;
  } catch {
    /* localStorage 可能被擋，用預設值 */
  }
  return DEFAULT_CHAT_WIDTH;
}

/**
 * 左欄（聊天）寬度：拖分隔線調整，記在 localStorage。
 * 回傳的 onPointerDown 掛在分隔線上；拖動期間 dragging=true。
 */
export function useSplitWidth() {
  const [width, setWidth] = useState<number>(() => (typeof window === "undefined" ? DEFAULT_CHAT_WIDTH : readStored()));
  const [dragging, setDragging] = useState(false);
  const startRef = useRef<{ x: number; width: number } | null>(null);

  useEffect(() => {
    try {
      localStorage.setItem(KEY, String(width));
    } catch {
      /* ignore */
    }
  }, [width]);

  useEffect(() => {
    const onResize = () => setWidth((w) => clamp(w));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const onPointerDown = useCallback(
    (e: ReactPointerEvent<HTMLElement>) => {
      if (e.button !== 0) return;
      e.preventDefault();
      startRef.current = { x: e.clientX, width };
      setDragging(true);
      const target = e.currentTarget;
      target.setPointerCapture(e.pointerId);

      const onMove = (ev: PointerEvent) => {
        if (!startRef.current) return;
        setWidth(clamp(startRef.current.width + (ev.clientX - startRef.current.x)));
      };
      const onUp = () => {
        startRef.current = null;
        setDragging(false);
        target.removeEventListener("pointermove", onMove);
        target.removeEventListener("pointerup", onUp);
        target.removeEventListener("pointercancel", onUp);
      };
      target.addEventListener("pointermove", onMove);
      target.addEventListener("pointerup", onUp);
      target.addEventListener("pointercancel", onUp);
    },
    [width],
  );

  const reset = useCallback(() => setWidth(DEFAULT_CHAT_WIDTH), []);

  return { width, dragging, onPointerDown, reset };
}
