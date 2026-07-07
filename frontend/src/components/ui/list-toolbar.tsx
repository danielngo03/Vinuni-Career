"use client";

import { MagnifyingGlass, X } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

/* -------------------------------------------------------------------------
 * SearchInput — the one shared search field for list/table surfaces. Replaces
 * ~24 hand-rolled MagnifyingGlass inputs. Debouncing stays the caller's job
 * (surfaces already debounce their query keys).
 * ---------------------------------------------------------------------- */
export interface SearchInputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "onChange" | "value"> {
  value: string;
  onValueChange: (value: string) => void;
  /** Shows a clear affordance while non-empty. */
  onClear?: () => void;
  ariaLabel: string;
}

export function SearchInput({
  value,
  onValueChange,
  onClear,
  ariaLabel,
  className,
  placeholder,
  ...props
}: SearchInputProps) {
  return (
    <div className={cn("relative min-w-0 flex-1", className)}>
      <MagnifyingGlass
        aria-hidden
        weight="bold"
        className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-[var(--text-muted)]"
      />
      <input
        type="search"
        value={value}
        aria-label={ariaLabel}
        placeholder={placeholder}
        onChange={(e) => onValueChange(e.target.value)}
        className={cn(
          "h-10 w-full rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] pl-9 pr-9 text-sm text-[var(--text-primary)]",
          "outline-none transition-colors placeholder:text-[var(--text-muted)]",
          "hover:border-[var(--border-strong)] focus:border-[var(--field-focus-border)] focus:ring-4 focus:ring-[var(--field-focus-ring)]",
          "[&::-webkit-search-cancel-button]:appearance-none",
        )}
        {...props}
      />
      {value && onClear && (
        <button
          type="button"
          onClick={onClear}
          aria-label={`${ariaLabel} — clear`}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-[var(--text-muted)] outline-none transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
        >
          <X aria-hidden weight="bold" className="size-3.5" />
        </button>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------
 * FilterChip — toggle pill for faceted filters. aria-pressed for state.
 * ---------------------------------------------------------------------- */
export interface FilterChipProps {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  /** Optional count badge (e.g. matches in this facet). */
  count?: number;
  icon?: React.ReactNode;
}

export function FilterChip({ active, onClick, children, count, icon }: FilterChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-3 py-1.5 text-xs font-semibold outline-none transition-colors",
        "focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30 focus-visible:ring-offset-1 motion-reduce:transition-none",
        active
          ? "border-transparent bg-[var(--btn-primary-bg)] text-[var(--btn-primary-fg)]"
          : "border-[var(--border-default)] bg-[var(--surface-card)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
      )}
    >
      {icon}
      {children}
      {count != null && (
        <span
          className={cn(
            "rounded-full px-1.5 text-[10px] font-bold tabular-nums",
            active ? "bg-[var(--btn-primary-fg)]/20" : "bg-[var(--bg-muted)] text-[var(--text-muted)]",
          )}
        >
          {count}
        </span>
      )}
    </button>
  );
}

/* -------------------------------------------------------------------------
 * ListToolbar — the standard list/table header: search + filters + actions
 * (sort / view toggle / export) + a result-count line. Every slot optional;
 * pure layout so any surface composes its own controls consistently.
 * ---------------------------------------------------------------------- */
export interface ListToolbarProps {
  search?: React.ReactNode;
  /** Faceted filter chips/selects (wrap on mobile). */
  filters?: React.ReactNode;
  /** Right-aligned controls: sort, ViewToggle, ExportButton. */
  actions?: React.ReactNode;
  /** Result count / freshness line rendered under the controls. */
  count?: React.ReactNode;
  className?: string;
}

export function ListToolbar({ search, filters, actions, count, className }: ListToolbarProps) {
  return (
    <div className={cn("flex flex-col gap-3", className)}>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        {search}
        {filters && (
          <div className="flex flex-wrap items-center gap-2">{filters}</div>
        )}
        {actions && (
          <div className="flex items-center gap-2 sm:ml-auto">{actions}</div>
        )}
      </div>
      {count && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--text-muted)]">
          {count}
        </div>
      )}
    </div>
  );
}
