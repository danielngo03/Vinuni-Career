"use client";

import { useRef } from "react";
import { cn } from "@/lib/utils";

export interface ViewOption {
  value: string;
  /** Accessible label for this view (also the hover/focus title). */
  label: string;
  icon: React.ReactNode;
}

export interface ViewToggleProps {
  value: string;
  onValueChange: (value: string) => void;
  options: ViewOption[];
  ariaLabel: string;
  size?: "sm" | "md";
}

/**
 * Icon-only view switcher (card / list / grid / table). A radiogroup with
 * roving arrow-key navigation (WAI-ARIA). Standardizes the per-screen
 * bespoke view toggles (e.g. jobs board list/grid) onto one primitive.
 */
export function ViewToggle({
  value,
  onValueChange,
  options,
  ariaLabel,
  size = "md",
}: ViewToggleProps) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onKeyDown(e: React.KeyboardEvent) {
    const idx = options.findIndex((o) => o.value === value);
    if (idx === -1) return;
    let next = idx;
    if (e.key === "ArrowRight" || e.key === "ArrowDown")
      next = (idx + 1) % options.length;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp")
      next = (idx - 1 + options.length) % options.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = options.length - 1;
    else return;
    e.preventDefault();
    const target = options[next]!;
    onValueChange(target.value);
    refs.current[target.value]?.focus();
  }

  const box = size === "sm" ? "size-7" : "size-8";

  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      onKeyDown={onKeyDown}
      className="inline-flex gap-0.5 rounded-xl border border-[var(--border-default)] p-0.5"
    >
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            ref={(el) => {
              refs.current[option.value] = el;
            }}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={option.label}
            title={option.label}
            tabIndex={selected ? 0 : -1}
            onClick={() => onValueChange(option.value)}
            className={cn(
              "inline-flex items-center justify-center rounded-lg outline-none transition-colors motion-reduce:transition-none",
              "focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30 focus-visible:ring-offset-1",
              box,
              selected
                ? "bg-[var(--btn-primary-bg)] text-[var(--btn-primary-fg)]"
                : "bg-transparent text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)]",
            )}
          >
            {option.icon}
          </button>
        );
      })}
    </div>
  );
}
