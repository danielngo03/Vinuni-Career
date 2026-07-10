"use client";

import * as React from "react";
import { ChevronDown } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { initials } from "./chip-tones";

/**
 * Shared toolbar primitives for the org-wide recruiting boards (interviews +
 * offers). Kept restyle-consistent with the candidates-screen toolbar so the
 * partner workspace feels like one product.
 */

/** Segmented single-select chip group (scope / status). Stable-height row. */
export function SegmentedFilter<T extends string>({
  value,
  options,
  onChange,
  label,
  optionLabel,
}: {
  value: T;
  options: readonly T[];
  onChange: (next: T) => void;
  /** Accessible group label. */
  label: string;
  optionLabel: (option: T) => string;
}) {
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label={label}>
      {options.map((opt) => {
        const active = value === opt;
        return (
          <button
            key={opt}
            type="button"
            onClick={() => onChange(opt)}
            aria-pressed={active}
            className={
              active
                ? "rounded-lg border border-transparent bg-foreground px-3 py-1.5 text-[0.8125rem] font-semibold text-background"
                : "rounded-lg border border-border bg-card px-3 py-1.5 text-[0.8125rem] font-medium text-muted-foreground transition-colors hover:text-foreground"
            }
          >
            {optionLabel(opt)}
          </button>
        );
      })}
    </div>
  );
}

/** Toolbar dropdown-select (label + current value) — for status/job filters. */
export function BoardToolbarMenu({
  icon: Icon,
  label,
  value,
  children,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  children: React.ReactNode;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border bg-card px-3 text-[0.8125rem] font-medium text-foreground outline-none transition-colors hover:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
        >
          <Icon aria-hidden className="size-4 text-muted-foreground" strokeWidth={1.8} />
          <span className="text-muted-foreground">{label}:</span>
          <span className="max-w-[10rem] truncate">{value}</span>
          <ChevronDown aria-hidden className="size-3.5 text-muted-foreground" strokeWidth={1.8} />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-[20rem] min-w-[13rem] overflow-y-auto">
        {children}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Radio-select body for {@link BoardToolbarMenu}. */
export function BoardToolbarRadio<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (next: T) => void;
}) {
  return (
    <>
      <DropdownMenuLabel>{label}</DropdownMenuLabel>
      <DropdownMenuRadioGroup value={value} onValueChange={(v) => onChange(v as T)}>
        {options.map((o) => (
          <DropdownMenuRadioItem key={o.value} value={o.value}>
            {o.label}
          </DropdownMenuRadioItem>
        ))}
      </DropdownMenuRadioGroup>
    </>
  );
}

/** Overlapping avatar stack for interview assignees (up to 3 + overflow). */
export function AssigneeStack({
  names,
  extra,
  emptyLabel,
}: {
  names: string[];
  /** Total minus shown (e.g. assignee_count - names.length), floored at 0. */
  extra: number;
  emptyLabel: string;
}) {
  if (names.length === 0 && extra <= 0) {
    return <span className="type-caption text-muted-foreground">{emptyLabel}</span>;
  }
  return (
    <span className="inline-flex items-center">
      <span className="flex -space-x-1.5">
        {names.map((name, i) => (
          <Avatar
            key={`${name}-${i}`}
            size="sm"
            className="ring-2 ring-background"
            title={name}
          >
            <AvatarFallback>{initials(name)}</AvatarFallback>
          </Avatar>
        ))}
      </span>
      {extra > 0 && (
        <span className="ml-1.5 type-caption font-medium tabular-nums text-muted-foreground">
          +{extra}
        </span>
      )}
    </span>
  );
}

const AMOUNT_FMT = new Intl.NumberFormat("vi-VN");

/**
 * Format offer comp as "{amount} {currency}/{period}" (e.g.
 * "20.000.000 VND/tháng"). Returns null when no figure was set — the caller
 * renders an em dash so the column stays aligned.
 */
export function formatSalary(
  amount: number | null,
  currency: string,
  periodLabel: string,
): string | null {
  if (amount == null) return null;
  const money = `${AMOUNT_FMT.format(amount)} ${currency}`;
  return periodLabel ? `${money}/${periodLabel}` : money;
}
