import * as React from "react";
import { cn } from "../../lib/utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "success" | "warning" | "danger" | "outline";
}

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <div
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent",
        {
          "border-transparent bg-surface-3 text-text-primary": variant === "default",
          "border-transparent bg-success-muted text-success": variant === "success",
          "border-transparent bg-warning-muted text-warning": variant === "warning",
          "border-transparent bg-danger-muted text-danger": variant === "danger",
          "border-border-default text-text-secondary": variant === "outline",
        },
        className
      )}
      {...props}
    />
  );
}
