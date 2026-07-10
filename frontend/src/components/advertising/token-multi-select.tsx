"use client";

import * as React from "react";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

export interface TokenOption {
  value: string;
  label: string;
}

/**
 * A coarse, allowlist-only multiselect rendered as toggle chips. Used for
 * campaign COARSE targeting (location / major / career / work-mode / cohort) —
 * the operator can only pick from the fixed vocabulary, never type a free-text
 * GPS/exact-location value. Accessible: each chip is a toggle button with
 * `aria-pressed`; the group is a labelled fieldset.
 */
export function TokenMultiSelect({
  label,
  hint,
  options,
  value,
  onChange,
}: {
  label: string;
  hint?: string;
  options: TokenOption[];
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const selected = React.useMemo(() => new Set(value), [value]);

  function toggle(v: string) {
    const next = new Set(selected);
    if (next.has(v)) next.delete(v);
    else next.add(v);
    onChange([...next]);
  }

  return (
    <fieldset className="min-w-0">
      <legend className="mb-1.5 block text-sm font-semibold text-foreground">
        {label}
      </legend>
      <div className="flex flex-wrap gap-1.5">
        {options.map((o) => {
          const active = selected.has(o.value);
          return (
            <button
              key={o.value}
              type="button"
              aria-pressed={active}
              onClick={() => toggle(o.value)}
              className={cn(
                "inline-flex items-center gap-1 rounded-full border px-3 py-1 text-[0.8125rem] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]",
                active
                  ? "border-transparent bg-foreground text-[var(--surface-card)]"
                  : "border-border bg-card text-muted-foreground hover:text-foreground",
              )}
            >
              {active && <Check className="size-3 shrink-0" strokeWidth={2.6} />}
              {o.label}
            </button>
          );
        })}
      </div>
      {hint && <p className="mt-1.5 type-caption text-muted-foreground">{hint}</p>}
    </fieldset>
  );
}
