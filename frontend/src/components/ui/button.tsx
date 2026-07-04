"use client";

import { forwardRef } from "react";
import { cn } from "@/lib/utils";

type Variant =
  | "primary"
  | "primaryRed"
  | "secondary"
  | "ghost"
  | "danger";
type Size = "xs" | "sm" | "md" | "lg" | "xl";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-[var(--btn-primary-bg)] text-[var(--btn-primary-fg)] font-semibold shadow-[var(--shadow-brand)] hover:bg-[var(--btn-primary-hover)] focus-visible:outline-[var(--border-focus)]",
  primaryRed:
    "bg-[var(--brand-red)] text-white font-semibold shadow-[var(--shadow-red)] hover:bg-[var(--red-700)] active:bg-[var(--red-800)] focus-visible:outline-[var(--red-400)]",
  secondary:
    "bg-[var(--surface-card)] text-[var(--text-primary)] border border-[var(--border-strong)] font-semibold hover:bg-[var(--bg-subtle)] hover:border-[var(--text-muted)]",
  ghost:
    "bg-transparent text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)]",
  danger:
    "bg-[var(--brand-red)] text-white font-semibold shadow-[var(--shadow-red)] hover:bg-[var(--red-700)] active:bg-[var(--red-800)]",
};

/* Pill geometry — the v7.1 reference look: fully rounded actions at every size. */
const SIZES: Record<Size, string> = {
  xs: "h-7 px-3 text-xs rounded-full gap-1",
  sm: "h-8 px-3.5 text-xs rounded-full gap-1.5",
  md: "h-9 px-4.5 text-sm rounded-full gap-2",
  lg: "h-10 px-5 text-sm rounded-full gap-2",
  xl: "h-12 px-6 text-base rounded-full gap-2.5",
};

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  fullWidth?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      className,
      variant = "primary",
      size = "md",
      loading = false,
      fullWidth = false,
      disabled,
      children,
      type = "button",
      ...props
    },
    ref,
  ) {
    return (
      <button
        ref={ref}
        type={type}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        className={cn(
          "inline-flex items-center justify-center whitespace-nowrap transition-colors duration-150 outline-none",
          "disabled:cursor-not-allowed disabled:opacity-50",
          VARIANTS[variant],
          SIZES[size],
          fullWidth && "w-full",
          className,
        )}
        {...props}
      >
        {loading && (
          <span
            aria-hidden
            className="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
          />
        )}
        {children}
      </button>
    );
  },
);
