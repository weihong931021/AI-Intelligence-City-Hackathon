import { XIcon } from "lucide-react";
import { type ReactNode, useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";

import { Button } from "./button";

/** 原生 modal 提供焦點限制、Escape 與關閉後焦點還原。只在開啟時掛載。 */
export function Dialog({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  const headingId = useId();
  useEffect(() => {
    const dialog = ref.current!;
    const previousFocus = document.activeElement as HTMLElement | null;
    dialog.showModal();
    return () => { dialog.close(); previousFocus?.focus(); };
  }, []);

  return createPortal(
    <dialog
      ref={ref}
      aria-labelledby={headingId}
      onCancel={(e) => { e.preventDefault(); onClose(); }}
      onKeyDown={(e) => e.stopPropagation()}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      className="m-auto max-h-[85dvh] w-[calc(100%-2rem)] max-w-xl overflow-y-auto rounded-3xl border border-border bg-[#1c1c1c] p-0 text-foreground shadow-2xl backdrop:bg-black/65"
    >
      <div className="p-5 sm:p-6">
        <div className="mb-5 flex items-center justify-between gap-3">
          <h2 id={headingId} className="text-lg font-medium">{title}</h2>
          <Button type="button" variant="chrome" size="icon-sm" aria-label="關閉視窗" onClick={onClose}><XIcon /></Button>
        </div>
        {children}
      </div>
    </dialog>,
    document.body,
  );
}
