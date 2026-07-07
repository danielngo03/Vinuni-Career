"use client";

import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import type { LanguageRequirement } from "@/lib/api/jobs";
import { RepeatableRows } from "./RepeatableRows";

export interface LanguageRowsLabels {
  language: string;
  proficiency: string;
  required: string;
  addRow: string;
}

export interface LanguageRowsProps {
  value: LanguageRequirement[];
  onChange: (v: LanguageRequirement[]) => void;
  disabled?: boolean;
  labels: LanguageRowsLabels;
}

function emptyLanguageRow(): LanguageRequirement {
  return { language: "", proficiency: null, required: false };
}

/**
 * Repeatable language requirement rows using RepeatableRows generic.
 * Each row: language Input + proficiency Input (optional) + required Switch.
 */
export function LanguageRows({
  value,
  onChange,
  disabled,
  labels,
}: LanguageRowsProps) {
  return (
    <RepeatableRows<LanguageRequirement>
      items={value}
      onChange={onChange}
      emptyRow={emptyLanguageRow}
      addLabel={labels.addRow}
      disabled={disabled}
      renderRow={(item, _i, update) => (
        <div className="flex flex-wrap items-end gap-2">
          <div className="w-40 min-w-[120px]">
            <Input
              label={labels.language}
              value={item.language}
              onChange={(e) => update({ ...item, language: e.target.value })}
              disabled={disabled}
              aria-label={labels.language}
            />
          </div>
          <div className="w-36 min-w-[100px]">
            <Input
              label={labels.proficiency}
              value={item.proficiency ?? ""}
              onChange={(e) =>
                update({ ...item, proficiency: e.target.value || null })
              }
              disabled={disabled}
              aria-label={labels.proficiency}
            />
          </div>
          <div className="mb-2.5 flex items-center">
            <Switch
              checked={item.required}
              onCheckedChange={(checked) => update({ ...item, required: checked })}
              disabled={disabled}
              label={labels.required}
            />
          </div>
        </div>
      )}
    />
  );
}
