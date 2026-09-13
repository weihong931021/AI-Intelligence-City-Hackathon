import { useCallback, useEffect, useRef, useState } from "react";

export function useCopyToClipboard({ copiedDuration = 2000 } = {}) {
  const [isCopied, setIsCopied] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  const copyToClipboard = useCallback(
    (value: string) => {
      if (!value) return;
      navigator.clipboard.writeText(value).then(() => {
        setIsCopied(true);
        if (timeoutRef.current) clearTimeout(timeoutRef.current);
        timeoutRef.current = setTimeout(() => setIsCopied(false), copiedDuration);
      });
    },
    [copiedDuration],
  );

  return { isCopied, copyToClipboard };
}
