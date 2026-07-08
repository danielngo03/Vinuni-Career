"use client";

import { Trash, Plus } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export interface RepeatableRowsProps<T> {
  items: T[];
  onChange: (items: T[]) => void;
  renderRow: (item: T, index: number, update: (next: T) => void) => React.ReactNode;
  emptyRow: () => T;
  addLabel: string;
  disabled?: boolean;
}

/**
 * Generic add/remove list. Controlled — caller owns the array.
 * Renders a ghost Trash button per row (red on hover) and an add button below.
 */
export function RepeatableRows<T>({
  items,
  onChange,
  renderRow,
  emptyRow,
  addLabel,
  disabled,
}: RepeatableRowsProps<T>) {
  function handleAdd() {
    onChange([...items, emptyRow()]);
  }

  function handleRemove(idx: number) {
    onChange(items.filter((_, i) => i !== idx));
  }

  function handleUpdate(idx: number, next: T) {
    onChange(items.map((item, i) => (i === idx ? next : item)));
  }

  return (
    <div className="space-y-2">
      {items.map((item, i) => (
        <div key={i} className="flex items-start gap-2">
          <div className="flex-1">{renderRow(item, i, (next) => handleUpdate(i, next))}</div>
          <button
            type="button"
            aria-label="Remove row"
            disabled={disabled}
            onClick={() => handleRemove(i)}
            className={cn(
              "mt-2.5 flex items-center justify-center rounded-lg p-1.5 outline-none transition-colors duration-100",
              "text-[var(--text-muted)] hover:text-[var(--color-error)]",
              "focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30",
              disabled && "cursor-not-allowed opacity-50",
            )}
          >
            <Trash size={16} />
          </button>
        </div>
      ))}
      <Button
        type="button"
        variant="ghost"
        size="sm"
        disabled={disabled}
        onClick={handleAdd}
        className="gap-1.5"
      >
        <Plus size={14} />
        {addLabel}
      </Button>
    </div>
  );
}
