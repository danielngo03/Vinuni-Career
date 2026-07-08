"use client";

import { useRef, useState } from "react";
import { X } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

export interface TagPreset {
  value: string;
  label: string;
}

export interface TagInputProps {
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
  presets?: TagPreset[];
  disabled?: boolean;
  ariaLabel: string;
}

/**
 * Chips input.
 * - Type + Enter (or comma) to add a value.
 * - Backspace on empty text removes the last chip.
 * - Click × on a chip to remove it.
 * - Optional preset suggestions shown as clickable chips below the input.
 */
export function TagInput({
  value,
  onChange,
  placeholder,
  presets,
  disabled,
  ariaLabel,
}: TagInputProps) {
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  function addValue(raw: string) {
    const trimmed = raw.trim();
    if (!trimmed || value.includes(trimmed)) return;
    onChange([...value, trimmed]);
  }

  function removeAt(idx: number) {
    onChange(value.filter((_, i) => i !== idx));
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      addValue(draft);
      setDraft("");
    } else if (e.key === "Backspace" && draft === "" && value.length > 0) {
      removeAt(value.length - 1);
    }
  }

  function handlePresetClick(preset: TagPreset) {
    if (value.includes(preset.value)) {
      // Toggle off
      onChange(value.filter((v) => v !== preset.value));
    } else {
      onChange([...value, preset.value]);
    }
  }

  const presetValueSet = new Set(value);

  return (
    <div
      className={cn("space-y-2", disabled && "pointer-events-none opacity-60")}
    >
      {/* Input + chips container */}
      <div
        className={cn(
          "flex min-h-[42px] flex-wrap gap-1.5 rounded-xl border bg-transparent px-3 py-2",
          "border-[var(--border-default)] transition-[border-color,box-shadow] duration-150",
          "focus-within:border-[var(--field-focus-border)] focus-within:shadow-[0_0_0_4px_var(--field-focus-ring)]",
        )}
        onClick={() => inputRef.current?.focus()}
      >
        {value.map((chip, i) => (
          <span
            key={chip + i}
            className="inline-flex items-center gap-1 rounded-full bg-[var(--bg-subtle)] px-2.5 py-1 text-xs font-medium text-[var(--text-primary)]"
          >
            {chip}
            {!disabled && (
              <button
                type="button"
                aria-label={`Remove ${chip}`}
                onClick={(e) => {
                  e.stopPropagation();
                  removeAt(i);
                }}
                className="flex items-center justify-center rounded-full text-[var(--text-muted)] outline-none hover:text-[var(--text-primary)] focus-visible:ring-1 focus-visible:ring-[var(--brand-primary)]"
              >
                <X size={10} weight="bold" />
              </button>
            )}
          </span>
        ))}
        <input
          ref={inputRef}
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={() => {
            if (draft.trim()) {
              addValue(draft);
              setDraft("");
            }
          }}
          disabled={disabled}
          placeholder={value.length === 0 ? placeholder : undefined}
          aria-label={ariaLabel}
          className="min-w-[120px] flex-1 bg-transparent text-sm font-medium text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
        />
      </div>

      {/* Preset suggestions */}
      {presets && presets.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {presets.map((preset) => {
            const active = presetValueSet.has(preset.value);
            return (
              <button
                key={preset.value}
                type="button"
                disabled={disabled}
                onClick={() => handlePresetClick(preset)}
                className={cn(
                  "inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium transition-colors duration-100",
                  "outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30",
                  active
                    ? "border-[var(--brand-primary)] bg-[var(--brand-primary)] text-[var(--btn-primary-fg)]"
                    : "border-[var(--border-default)] bg-transparent text-[var(--text-secondary)] hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]",
                )}
              >
                {preset.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
