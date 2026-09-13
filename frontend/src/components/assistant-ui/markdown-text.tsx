import "@assistant-ui/react-markdown/styles/dot.css";

import {
  MarkdownTextPrimitive,
  unstable_memoizeMarkdownComponents as memoizeMarkdownComponents,
  useIsMarkdownCodeBlock,
} from "@assistant-ui/react-markdown";
import remarkGfm from "remark-gfm";
import { type FC, memo } from "react";

import { cn } from "@/lib/utils";

const MarkdownTextImpl: FC = () => {
  return (
    <MarkdownTextPrimitive
      remarkPlugins={[remarkGfm]}
      className="aui-md"
      components={defaultComponents}
      defer
    />
  );
};

export const MarkdownText = memo(MarkdownTextImpl);

const defaultComponents = memoizeMarkdownComponents({
  h1: ({ className, ...props }) => (
    <h1 className={cn("mt-4 mb-2 text-lg font-semibold first:mt-0 last:mb-0", className)} {...props} />
  ),
  h2: ({ className, ...props }) => (
    <h2 className={cn("mt-4 mb-2 text-base font-semibold first:mt-0 last:mb-0", className)} {...props} />
  ),
  h3: ({ className, ...props }) => (
    <h3 className={cn("mt-3 mb-1.5 text-sm font-semibold first:mt-0 last:mb-0", className)} {...props} />
  ),
  p: ({ className, ...props }) => (
    <p className={cn("my-2.5 leading-[inherit] first:mt-0 last:mb-0", className)} {...props} />
  ),
  a: ({ className, ...props }) => (
    <a className={cn("text-primary underline underline-offset-2 hover:text-primary/80", className)} {...props} />
  ),
  ul: ({ className, ...props }) => (
    <ul className={cn("my-2.5 ms-5 list-disc marker:text-muted-foreground [&>li]:mt-1", className)} {...props} />
  ),
  ol: ({ className, ...props }) => (
    <ol className={cn("my-2.5 ms-5 list-decimal marker:text-muted-foreground [&>li]:mt-1", className)} {...props} />
  ),
  li: ({ className, ...props }) => <li className={cn("leading-[inherit]", className)} {...props} />,
  strong: ({ className, ...props }) => <strong className={cn("font-semibold", className)} {...props} />,
  hr: ({ className, ...props }) => <hr className={cn("my-3 border-muted-foreground/20", className)} {...props} />,
  table: ({ className, ...props }) => (
    <div className="my-3 overflow-x-auto">
      <table className={cn("w-full border-separate border-spacing-0", className)} {...props} />
    </div>
  ),
  th: ({ className, ...props }) => (
    <th className={cn("bg-muted px-3 py-1.5 text-start font-medium", className)} {...props} />
  ),
  td: ({ className, ...props }) => (
    <td className={cn("border-b border-s border-muted-foreground/20 px-3 py-1.5 last:border-e", className)} {...props} />
  ),
  pre: ({ className, ...props }) => (
    <pre
      className={cn("my-3 overflow-x-auto rounded-xl border border-border/50 bg-muted/30 p-3.5 text-[13px] leading-relaxed", className)}
      {...props}
    />
  ),
  code: function Code({ className, ...props }) {
    const isCodeBlock = useIsMarkdownCodeBlock();
    return (
      <code
        className={cn(!isCodeBlock && "rounded-md bg-muted px-1.5 py-0.5 font-mono text-[0.85em]", className)}
        {...props}
      />
    );
  },
});
