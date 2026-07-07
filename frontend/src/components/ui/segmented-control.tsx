"use client";

import { useRef } from "react";
import { cn } from "@/lib/utils";

export interface SegmentedOption {
  value: string;
  label: string;
}

export interface SegmentedControlProps {
  value: string;
  onValueChange: (value: string) => void;
  options: SegmentedOption[];
  ariaLabel: string;
  size?: "sm" | "md";
  disabled?: boolean;
  id?: string;
}

/**
 * Accessible pill segmented control rendered as a radiogroup.
 * Roving arrow-key navigation (ArrowLeft/Right, Home/End) per WAI-ARIA.
 * Uses v9 Monochrome design tokens only — no ad-hoc hues.
 */
export function SegmentedControl({
  value,
  onValueChange,
  options,
  ariaLabel,
  size = "md",
  disabled = false,
  id,
}: SegmentedControlProps) {
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

  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      aria-disabled={disabled}
      id={id}
      onKeyDown={disabled ? undefined : onKeyDown}
      className={cn(
        "inline-flex gap-0.5 rounded-xl border border-[var(--border-default)] p-0.5",
        disabled && "pointer-events-none opacity-60",
      )}
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
            tabIndex={selected ? 0 : -1}
            disabled={disabled}
            onClick={() => onValueChange(option.value)}
            className={cn(
              "inline-flex items-center whitespace-nowrap rounded-lg font-medium outline-none transition-colors motion-reduce:transition-none",
              "focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30 focus-visible:ring-offset-1",
              size === "sm" ? "px-2.5 py-1 text-xs" : "px-3 py-1.5 text-sm",
              selected
                ? "bg-[var(--btn-primary-bg)] text-[var(--btn-primary-fg)]"
                : "bg-transparent text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)]",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
