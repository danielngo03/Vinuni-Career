export function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-[var(--glass-border)] bg-[var(--glass-surface-light)] px-3.5 py-2.5 backdrop-blur-sm">
      <dt className="text-xs font-medium text-[var(--text-muted)]">{label}</dt>
      <dd className="mt-0.5 text-sm font-semibold text-[var(--text-primary)]">
        {children}
      </dd>
    </div>
  );
}
