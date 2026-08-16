import * as React from "react";
import { cn } from "../../lib/utils";

export function Kbd({ className, children, ...props }: React.HTMLAttributes<HTMLElement>) {
  return (
    <kbd
      className={cn(
        "pointer-events-none inline-flex h-5 select-none items-center gap-1 rounded border border-border-default bg-surface-2 px-1.5 font-mono text-[10px] font-medium text-text-tertiary",
        className
      )}
      {...props}
    >
      {children}
    </kbd>
  );
}
