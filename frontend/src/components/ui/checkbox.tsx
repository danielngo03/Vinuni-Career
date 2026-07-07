"use client";

import { forwardRef, useEffect, useRef } from "react";
import { cn } from "@/lib/utils";

export interface CheckboxProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> {
  /** Tri-state: renders the indeterminate glyph (header select-all, partial). */
  indeterminate?: boolean;
  /** Accessible label — required (checkboxes are often icon-only in tables). */
  label: string;
}

/**
 * Accessible checkbox with indeterminate support and stable dimensions.
 * v9 Monochrome tokens only; visible focus ring; safe in light + dark themes.
 * Generalizes the feature-scoped `moderation/queue-controls#RowSelectCheckbox`.
 */
export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  function Checkbox({ indeterminate = false, label, className, ...props }, ref) {
    const innerRef = useRef<HTMLInputElement>(null);

    // Merge the forwarded ref with the local one used to set `.indeterminate`.
    useEffect(() => {
      if (innerRef.current) innerRef.current.indeterminate = indeterminate;
    }, [indeterminate]);

    return (
      <input
        ref={(node) => {
          innerRef.current = node;
          if (typeof ref === "function") ref(node);
          else if (ref) ref.current = node;
        }}
        type="checkbox"
        aria-label={label}
        onClick={(e) => e.stopPropagation()}
        className={cn(
          "size-4 shrink-0 cursor-pointer rounded border-[var(--border-strong)]",
          "accent-[var(--brand-primary)]",
          "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-primary)]",
          "disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
        {...props}
      />
    );
  },
);
