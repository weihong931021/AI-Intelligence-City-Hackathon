import { type ComponentPropsWithRef, forwardRef } from "react";
import { Slottable } from "@radix-ui/react-slot";

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type TooltipIconButtonProps = ComponentPropsWithRef<typeof Button> & {
  tooltip: string;
  side?: "top" | "bottom" | "left" | "right";
};

/**
 * 有工具提示的圖示鈕。預設就是 Codex 頂列那種：28px 命中範圍、16px 灰圖示、滑過才有淡底色。
 * 要別的樣子（例如白色送出鈕）就傳 variant / size 蓋掉。
 */
export const TooltipIconButton = forwardRef<HTMLButtonElement, TooltipIconButtonProps>(
  ({ children, tooltip, side = "bottom", className, ...rest }, ref) => {
    return (
      <TooltipProvider delayDuration={0}>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="chrome"
              size="icon-sm"
              {...rest}
              className={cn("active:scale-95", className)}
              ref={ref}
            >
              <Slottable>{children}</Slottable>
              <span className="sr-only">{tooltip}</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent side={side}>{tooltip}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  },
);
TooltipIconButton.displayName = "TooltipIconButton";
