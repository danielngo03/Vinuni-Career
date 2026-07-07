"use client";

import { cn } from "@/lib/utils";
import { SegmentedControl } from "@/components/ui/segmented-control";
import type { RequirementGroup, RequirementMode } from "@/lib/api/jobs";
import { TagInput } from "./TagInput";
import type { TagPreset } from "./TagInput";

export interface RequirementGroupModeLabels {
  notRequired: string;
  required: string;
  preferred: string;
}

export interface RequirementGroupFieldProps {
  label: string;
  value: RequirementGroup;
  onChange: (v: RequirementGroup) => void;
  /** Variant of value control shown when mode != not_required. Currently only "chips". */
  variant?: "chips";
  presets?: TagPreset[];
  disabled?: boolean;
  modeLabels: RequirementGroupModeLabels;
  helpText?: string;
}

const MODE_OPTIONS = (labels: RequirementGroupModeLabels) => [
  { value: "not_required" as const, label: labels.notRequired },
  { value: "required" as const, label: labels.required },
  { value: "preferred" as const, label: labels.preferred },
];

/**
 * One eligibility row: a label, a mode SegmentedControl, and (when mode ≠
 * not_required) a value-entry control. Fully controlled.
 *
 * Keeps `values` and `note` intact when toggling mode so the user's data is
 * not lost if they toggle back.
 */
export function RequirementGroupField({
  label,
  value,
  onChange,
  variant = "chips",
  presets,
  disabled,
  modeLabels,
  helpText,
}: RequirementGroupFieldProps) {
  const options = MODE_OPTIONS(modeLabels);

  function handleModeChange(mode: string) {
    onChange({ ...value, mode: mode as RequirementMode });
  }

  function handleValuesChange(values: string[]) {
    onChange({ ...value, values });
  }

  const showValueControl = value.mode !== "not_required";

  return (
    <div className="space-y-2">
      <div
        className={cn(
          "flex flex-wrap items-center gap-3",
          disabled && "opacity-60",
        )}
      >
        <span className="min-w-[120px] text-sm font-semibold text-[var(--text-primary)]">
          {label}
        </span>
        <SegmentedControl
          value={value.mode}
          onValueChange={handleModeChange}
          options={options}
          ariaLabel={label}
          size="sm"
          disabled={disabled}
        />
      </div>

      {helpText && (
        <p className="text-xs text-[var(--text-secondary)]">{helpText}</p>
      )}

      {showValueControl && variant === "chips" && (
        <TagInput
          value={value.values}
          onChange={handleValuesChange}
          presets={presets}
          disabled={disabled}
          ariaLabel={label}
        />
      )}
    </div>
  );
}
