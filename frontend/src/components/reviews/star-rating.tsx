"use client";

import { Star } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

/** Read-only star display (supports halves via rounding to nearest 0.5). */
export function StarDisplay({
  value,
  size = 16,
  className,
}: {
  value: number | null;
  size?: number;
  className?: string;
}) {
  const v = value ?? 0;
  return (
    <span className={cn("inline-flex items-center gap-0.5", className)} aria-hidden>
      {[1, 2, 3, 4, 5].map((i) => (
        <Star
          key={i}
          size={size}
          weight={v >= i - 0.25 ? "fill" : "regular"}
          className={
            v >= i - 0.25
              ? "text-[var(--brand-amber,#d97706)]"
              : "text-[var(--text-muted)]"
          }
        />
      ))}
    </span>
  );
}

/** Interactive 1-5 star input (keyboard accessible via the radio group). */
export function StarInput({
  value,
  onChange,
  label,
}: {
  value: number;
  onChange: (v: number) => void;
  label: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="inline-flex items-center gap-1"
    >
      {[1, 2, 3, 4, 5].map((i) => (
        <button
          key={i}
          type="button"
          role="radio"
          aria-checked={value === i}
          aria-label={`${i} / 5`}
          onClick={() => onChange(i)}
          className="rounded outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
        >
          <Star
            size={24}
            weight={value >= i ? "fill" : "regular"}
            className={
              value >= i
                ? "text-[var(--brand-amber,#d97706)]"
                : "text-[var(--text-muted)] hover:text-[var(--brand-amber,#d97706)]"
            }
          />
        </button>
      ))}
    </div>
  );
}
