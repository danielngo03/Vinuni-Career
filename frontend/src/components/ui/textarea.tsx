"use client";

import { forwardRef, useId } from "react";
import { cn } from "@/lib/utils";

export interface TextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  required?: boolean;
  error?: string;
  help?: string;
}

/** Labeled, accessible multi-line input. Mirrors {@link Input} styling. */
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  function Textarea(
    { className, label, required, error, help, id, rows = 4, ...props },
    ref,
  ) {
    const generatedId = useId();
    const fieldId = id ?? generatedId;
    const errorId = `${fieldId}-error`;
    const helpId = `${fieldId}-help`;

    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={fieldId}
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
        <textarea
          ref={ref}
          id={fieldId}
          rows={rows}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={cn(error && errorId, help && helpId) || undefined}
          className={cn(
            "w-full resize-y rounded-xl border bg-transparent px-3.5 py-2.5 text-sm font-medium text-[var(--text-primary)]",
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
        {error ? (
          <p
            id={errorId}
            role="alert"
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
  },
);
