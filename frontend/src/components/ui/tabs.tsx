"use client";

import { useId, useRef } from "react";
import { cn } from "@/lib/utils";

export interface TabItem {
  value: string;
  label: string;
  icon?: React.ReactNode;
}

export interface TabsProps {
  items: TabItem[];
  value: string;
  onValueChange: (value: string) => void;
  ariaLabel?: string;
  className?: string;
  /** Stable id base shared with matching <TabPanel tabsId>. */
  idBase?: string;
}

/**
 * Accessible tab list with roving arrow-key navigation (WAI-ARIA tabs).
 * Panels are rendered by the caller, keyed off `value`.
 */
export function Tabs({
  items,
  value,
  onValueChange,
  ariaLabel,
  className,
  idBase,
}: TabsProps) {
  const generatedId = useId();
  const baseId = idBase ?? generatedId;
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onKeyDown(e: React.KeyboardEvent) {
    const idx = items.findIndex((i) => i.value === value);
    if (idx === -1) return;
    let next = idx;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") next = (idx + 1) % items.length;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp")
      next = (idx - 1 + items.length) % items.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = items.length - 1;
    else return;
    e.preventDefault();
    const target = items[next]!;
    onValueChange(target.value);
    refs.current[target.value]?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      onKeyDown={onKeyDown}
      className={cn(
        "mb-5 flex gap-2 overflow-x-auto",
        className,
      )}
    >
      {items.map((item) => {
        const selected = item.value === value;
        return (
          <button
            key={item.value}
            ref={(el) => {
              refs.current[item.value] = el;
            }}
            role="tab"
            id={`${baseId}-tab-${item.value}`}
            aria-selected={selected}
            aria-controls={`${baseId}-panel-${item.value}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onValueChange(item.value)}
            className={cn(
              "inline-flex items-center gap-2 whitespace-nowrap rounded-full border px-4 py-2 text-sm font-semibold outline-none transition-all focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30 focus-visible:ring-offset-1",
              selected
                ? "border-[var(--brand-primary)]/30 bg-[var(--brand-primary)] text-white shadow-sm shadow-[var(--brand-primary)]/20"
                : "border-white/60 bg-white/72 text-[var(--text-secondary)] backdrop-blur-sm hover:bg-white/90 hover:text-[var(--text-primary)]",
            )}
          >
            {item.icon}
            {item.label}
          </button>
        );
      })}
    </div>
  );
}

export function TabPanel({
  tabsId,
  value,
  active,
  children,
}: {
  tabsId: string;
  value: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <div
      role="tabpanel"
      id={`${tabsId}-panel-${value}`}
      aria-labelledby={`${tabsId}-tab-${value}`}
      hidden={!active}
      tabIndex={0}
      className="outline-none"
    >
      {active && children}
    </div>
  );
}
