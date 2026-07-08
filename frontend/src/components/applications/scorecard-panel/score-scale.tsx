"use client";

import { SCORE_VALUES } from "./utils";

export function ScoreScale({
  name,
  legend,
  value,
  onChange,
  disabled,
}: {
  name: string;
  legend: string;
  value: number | null;
  onChange: (n: number) => void;
  disabled?: boolean;
}) {
  return (
    <fieldset disabled={disabled} className="min-w-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <legend className="text-sm font-medium text-[var(--text-primary)]">
          {legend}
        </legend>
        <div role="radiogroup" aria-label={legend} className="flex gap-1.5">
          {SCORE_VALUES.map((n) => {
            const id = `${name}-${n}`;
            const checked = value === n;
            return (
              <label key={n} htmlFor={id} className="relative cursor-pointer">
                <input
                  type="radio"
                  id={id}
                  name={name}
                  value={n}
                  checked={checked}
                  onChange={() => onChange(n)}
                  className="peer sr-only"
                />
                <span className="flex size-9 items-center justify-center rounded-lg border border-[var(--border-default)] bg-[var(--bg-subtle)] text-sm font-semibold text-[var(--text-secondary)] transition-colors peer-checked:border-[var(--brand-primary)] peer-checked:bg-[var(--brand-primary)] peer-checked:text-white peer-focus-visible:ring-2 peer-focus-visible:ring-[var(--brand-primary)]/40">
                  {n}
                </span>
              </label>
            );
          })}
        </div>
      </div>
    </fieldset>
  );
}
