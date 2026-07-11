"use client";

import { forwardRef, useId } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export interface SelectOption {
  value: string;
  label: string;
  /** When true the option is shown but cannot be selected. */
  disabled?: boolean;
}

export interface SelectProps
  extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  required?: boolean;
  error?: string;
  help?: string;
  options: SelectOption[];
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className, label, required, error, help, options, id, ...props },
  ref,
) {
  const generatedId = useId();
  const selectId = id ?? generatedId;
  const errorId = `${selectId}-error`;
  const helpId = `${selectId}-help`;

  return (
    <div className="w-full">
      {label && (
        <label
          htmlFor={selectId}
          className="mb-1.5 block text-sm font-semibold text-[var(--text-primary)]"
        >
          {label}
          {required && (
            <span className="ml-0.5 text-[var(--brand-red)]" aria-hidden>
              *
            </span>
          )}
        </label>
      )}
      <div className="relative">
        <select
          ref={ref}
          id={selectId}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={cn(error && errorId, help && helpId) || undefined}
          className={cn(
            "w-full appearance-none rounded-xl border bg-transparent px-3.5 py-2.5 pr-10 text-sm font-medium text-[var(--text-primary)]",
            "outline-none transition-[border-color,box-shadow,background-color] duration-150",
            "focus:border-[var(--field-focus-border)] focus:bg-[var(--surface-card)] focus:shadow-[0_0_0_4px_var(--field-focus-ring)] focus:ring-0 focus-visible:outline-none",
            error
              ? "border-[var(--brand-red)] focus:border-[var(--brand-red)] focus:shadow-[0_0_0_4px_rgba(200,53,56,0.10)]"
              : "border-[var(--border-default)] hover:border-[var(--border-strong)]",
            "disabled:cursor-not-allowed disabled:opacity-60",
            className,
          )}
          {...props}
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value} disabled={opt.disabled}>
              {opt.label}
            </option>
          ))}
        </select>
        <ChevronDown
          aria-hidden
          strokeWidth={2.2}
          className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-[var(--text-muted)]"
        />
      </div>
      {error ? (
        <p
          id={errorId}
          className="mt-1 text-xs font-medium text-[var(--brand-red)]"
        >
          {error}
        </p>
      ) : help ? (
        <p id={helpId} className="mt-1 text-xs text-[var(--text-secondary)]">
          {help}
        </p>
      ) : null}
    </div>
  );
});
