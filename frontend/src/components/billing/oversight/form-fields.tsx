"use client";

/** Small, dependency-free form primitives shared by the billing oversight modals. */

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {label}
      </p>
      <div className="mt-0.5 text-sm text-[var(--text-primary)]">{children}</div>
    </div>
  );
}

export function LabeledTextarea({
  id,
  label,
  value,
  onChange,
  hint,
  error,
  rows = 3,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  hint?: string;
  error?: string;
  rows?: number;
}) {
  return (
    <div>
      <label
        htmlFor={id}
        className="mb-1.5 block text-sm font-semibold text-[var(--text-primary)]"
      >
        {label}
      </label>
      <textarea
        id={id}
        rows={rows}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-3.5 py-2.5 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--brand-primary)]/50 focus:bg-[var(--surface-card)] focus:ring-2 focus:ring-[var(--brand-primary)]/30"
      />
      {error && <p className="mt-1 text-xs font-medium text-[var(--red-700)]">{error}</p>}
      {hint && <p className="mt-1 text-xs text-[var(--text-muted)]">{hint}</p>}
    </div>
  );
}

export function SelectField({
  id,
  label,
  value,
  onChange,
  options,
  disabled = false,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  disabled?: boolean;
}) {
  return (
    <div>
      <label
        htmlFor={id}
        className="mb-1.5 block text-sm font-semibold text-[var(--text-primary)]"
      >
        {label}
      </label>
      <select
        id={id}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="h-10 w-full rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-3.5 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--brand-primary)]/50 focus:bg-[var(--surface-card)] focus:ring-2 focus:ring-[var(--brand-primary)]/30 disabled:opacity-60"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export function CheckboxField({
  id,
  label,
  checked,
  onChange,
}: {
  id: string;
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label
      htmlFor={id}
      className="inline-flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]"
    >
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="size-4 rounded border-[var(--border-default)] text-[var(--brand-primary)] focus:ring-[var(--brand-primary)]"
      />
      {label}
    </label>
  );
}
