import type * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full border font-medium text-sm transition-colors disabled:pointer-events-none disabled:opacity-45",
  {
    variants: {
      variant: {
        primary:
          "border-transparent bg-[var(--accent-strong)] text-[var(--accent-strong-foreground)] hover:bg-[var(--accent-strong-hover)]",
        secondary:
          "border-[var(--line)] bg-[var(--panel)] text-[var(--ink)] hover:bg-[var(--panel-soft)]",
        ghost:
          "border-transparent bg-transparent text-[var(--muted-ink)] hover:bg-[var(--panel-soft)] hover:text-[var(--ink)]",
        danger:
          "border-transparent bg-[var(--danger)] text-white hover:bg-[var(--danger-hover)]",
      },
      size: {
        md: "h-10 px-4",
        sm: "h-8 px-3 text-xs",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "secondary",
      size: "md",
    },
  },
);

export function Button({
  className,
  variant,
  size,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants>) {
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
