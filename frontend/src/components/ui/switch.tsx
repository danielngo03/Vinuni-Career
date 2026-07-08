"use client";

import { cn } from "@/lib/utils";

export interface SwitchProps {
  checked: boolean;
  onCheckedChange?: (checked: boolean) => void;
  disabled?: boolean;
  label: string;
  /** Visually hide the label but keep it for screen readers. */
  hideLabel?: boolean;
  id?: string;
}

/** Accessible toggle (role=switch). Color is paired with on/off position. */
export function Switch({
  checked,
  onCheckedChange,
  disabled,
  label,
  hideLabel,
  id,
}: SwitchProps) {
  return (
    <label
      htmlFor={id}
      className={cn(
        "inline-flex items-center gap-2",
        disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer",
      )}
    >
      <button
        type="button"
        id={id}
        role="switch"
        aria-checked={checked}
        aria-label={hideLabel ? label : undefined}
        disabled={disabled}
        onClick={() => onCheckedChange?.(!checked)}
        className={cn(
          "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full outline-none transition-colors",
          checked ? "bg-[var(--brand-primary)]" : "bg-[var(--gray-300)]",
        )}
      >
        <span
          aria-hidden
          className={cn(
            "inline-block size-4 transform rounded-full bg-white shadow transition-transform",
            checked ? "translate-x-4" : "translate-x-0.5",
          )}
        />
      </button>
      {!hideLabel && (
        <span className="text-sm font-medium text-[var(--text-primary)]">
          {label}
        </span>
      )}
    </label>
  );
}
