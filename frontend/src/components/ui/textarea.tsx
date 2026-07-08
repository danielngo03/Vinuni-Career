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
            "w-full resize-y rounded-xl border bg-white/80 px-3.5 py-2.5 text-sm font-medium text-[var(--text-primary)]",
            "placeholder:text-[var(--text-muted)] outline-none transition-all duration-150",
            "focus:border-[var(--brand-primary)] focus:bg-white/95 focus:ring-2 focus:ring-[var(--brand-primary)]/20",
            error
              ? "border-[var(--brand-red)] focus:border-[var(--brand-red)] focus:ring-[var(--brand-red)]/15"
              : "border-white/60 hover:border-[var(--border-default)]",
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
