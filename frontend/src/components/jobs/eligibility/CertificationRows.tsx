"use client";

import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import type { CertificationRequirement } from "@/lib/api/jobs";
import { RepeatableRows } from "./RepeatableRows";

export interface CertificationRowsLabels {
  name: string;
  required: string;
  addRow: string;
}

export interface CertificationRowsProps {
  value: CertificationRequirement[];
  onChange: (v: CertificationRequirement[]) => void;
  disabled?: boolean;
  labels: CertificationRowsLabels;
}

function emptyCertRow(): CertificationRequirement {
  return { name: "", required: false };
}

/**
 * Repeatable certification requirement rows using RepeatableRows generic.
 * Each row: certification name Input + required Switch.
 */
export function CertificationRows({
  value,
  onChange,
  disabled,
  labels,
}: CertificationRowsProps) {
  return (
    <RepeatableRows<CertificationRequirement>
      items={value}
      onChange={onChange}
      emptyRow={emptyCertRow}
      addLabel={labels.addRow}
      disabled={disabled}
      renderRow={(item, _i, update) => (
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex-1 min-w-[180px]">
            <Input
              label={labels.name}
              value={item.name}
              onChange={(e) => update({ ...item, name: e.target.value })}
              disabled={disabled}
              aria-label={labels.name}
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
