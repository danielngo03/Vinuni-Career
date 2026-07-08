"use client";

import { forwardRef, useId } from "react";
import { cn } from "@/lib/utils";

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  required?: boolean;
  error?: string;
  help?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, label, required, error, help, id, ...props },
  ref,
) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const errorId = `${inputId}-error`;
  const helpId = `${inputId}-help`;
  const showErrorInLabel = Boolean(label && error);

  return (
    <div className="w-full">
      {label && (
        <label
          htmlFor={inputId}
          className="mb-1.5 flex items-center justify-between gap-3 text-sm font-semibold text-[var(--text-primary)]"
        >
          <span>
            {label}
            {required && (
              <span className="ml-0.5 text-[var(--brand-red)]" aria-hidden>
                *
              </span>
            )}
          </span>
          {showErrorInLabel && (
            <span
              id={errorId}
              className="shrink-0 text-right text-xs font-semibold text-[var(--brand-red)]"
            >
              {error}
            </span>
          )}
        </label>
      )}
      <input
        ref={ref}
        id={inputId}
        required={required}
        aria-invalid={error ? true : undefined}
        aria-describedby={cn(error && errorId, help && helpId) || undefined}
        className={cn(
          "w-full rounded-xl border bg-transparent px-3.5 py-2.5 text-sm font-medium text-[var(--text-primary)]",
          "placeholder:text-[var(--text-muted)] outline-none transition-[border-color,box-shadow,background-color] duration-150",
          "focus:border-[var(--field-focus-border)] focus:bg-[var(--surface-card)] focus:shadow-[0_0_0_4px_var(--field-focus-ring)] focus:ring-0 focus-visible:outline-none",
          error
            ? "border-[var(--brand-red)] focus:border-[var(--brand-red)] focus:shadow-[0_0_0_4px_rgba(200,53,56,0.10)]"
            : "border-[var(--border-default)] hover:border-[var(--border-strong)]",
          "disabled:cursor-not-allowed disabled:opacity-60",
          className,
        )}
        {...props}
      />
      {error && !showErrorInLabel ? (
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
