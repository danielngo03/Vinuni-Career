"use client";

import { cn } from "@/lib/utils";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Input } from "@/components/ui/input";
import type { AgeRequirement, AgeMode } from "@/lib/api/jobs";

export interface AgeModeLabels {
  notRequired: string;
  atLeast: string;
  upTo: string;
  range: string;
  minLabel: string;
  maxLabel: string;
}

export interface AgeRequirementFieldProps {
  label: string;
  value: AgeRequirement;
  onChange: (v: AgeRequirement) => void;
  disabled?: boolean;
  modeLabels: AgeModeLabels;
}

const AGE_MIN = 14;
const AGE_MAX = 80;

/**
 * Age eligibility row: label + mode SegmentedControl + conditional number
 * inputs (min / max / both). Fully controlled.
 *
 * Keeps min/max values when toggling mode so data is preserved on toggling back.
 */
export function AgeRequirementField({
  label,
  value,
  onChange,
  disabled,
  modeLabels,
}: AgeRequirementFieldProps) {
  const options = [
    { value: "not_required" as const, label: modeLabels.notRequired },
    { value: "at_least" as const, label: modeLabels.atLeast },
    { value: "up_to" as const, label: modeLabels.upTo },
    { value: "range" as const, label: modeLabels.range },
  ];

  function handleModeChange(mode: string) {
    onChange({ ...value, mode: mode as AgeMode });
  }

  function handleMin(e: React.ChangeEvent<HTMLInputElement>) {
    const raw = e.target.value;
    onChange({ ...value, min: raw === "" ? null : Number(raw) });
  }

  function handleMax(e: React.ChangeEvent<HTMLInputElement>) {
    const raw = e.target.value;
    onChange({ ...value, max: raw === "" ? null : Number(raw) });
  }

  const showMin = value.mode === "at_least" || value.mode === "range";
  const showMax = value.mode === "up_to" || value.mode === "range";

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

      {(showMin || showMax) && (
        <div className="flex flex-wrap items-center gap-3">
          {showMin && (
            <div className="w-32">
              <Input
                type="number"
                min={AGE_MIN}
                max={AGE_MAX}
                label={modeLabels.minLabel}
                value={value.min ?? ""}
                onChange={handleMin}
                disabled={disabled}
                aria-label={modeLabels.minLabel}
              />
            </div>
          )}
          {showMax && (
            <div className="w-32">
              <Input
                type="number"
                min={AGE_MIN}
                max={AGE_MAX}
                label={modeLabels.maxLabel}
                value={value.max ?? ""}
                onChange={handleMax}
                disabled={disabled}
                aria-label={modeLabels.maxLabel}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
