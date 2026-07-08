export function CalmStatus({ title, hint }: { title: string; hint: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="mx-auto flex max-w-md flex-col items-center gap-3 py-16 text-center"
    >
      <span
        aria-hidden
        className="size-10 animate-spin rounded-full border-[3px] border-[var(--brand-primary)] border-t-transparent"
      />
      <p className="text-base font-semibold text-[var(--text-primary)]">{title}</p>
      <p className="text-xs text-[var(--text-muted)]">{hint}</p>
    </div>
  );
}
