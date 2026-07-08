export function BoardSkeleton() {
  return (
    <div className="flex gap-4 overflow-hidden pb-4" aria-hidden>
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="flex w-72 shrink-0 flex-col rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] "
        >
          <div className="border-b border-[var(--border-default)] px-3.5 py-3">
            <div className="h-4 w-24 animate-pulse rounded bg-[var(--bg-muted)]" />
          </div>
          <div className="flex flex-col gap-2.5 p-2.5">
            {Array.from({ length: 3 }).map((__, j) => (
              <div
                key={j}
                className="h-24 animate-pulse rounded-xl bg-[var(--surface-card)]"
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
