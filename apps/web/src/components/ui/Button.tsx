import * as React from "react";
import { cn } from "../../lib/utils";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "secondary", size = "md", ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center rounded-md font-ui font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-50",
          {
            "bg-accent text-white hover:bg-accent-hover": variant === "primary",
            "bg-surface-3 text-text-primary hover:bg-surface-4 border border-border-default": variant === "secondary",
            "bg-transparent text-text-secondary hover:bg-surface-3 hover:text-text-primary": variant === "ghost",
            "bg-danger text-white hover:bg-danger/90": variant === "danger",
            "h-6 px-2 text-xs": size === "sm",
            "h-8 px-3 text-sm": size === "md",
          },
          className
        )}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";
