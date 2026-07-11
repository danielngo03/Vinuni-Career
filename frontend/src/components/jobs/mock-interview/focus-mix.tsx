import { cn } from "@/lib/utils";

/** Canonical focus areas, in the order they should appear. Unknown keys sort
 *  after these by descending count so the layout stays stable and comparable. */
const FOCUS_ORDER = ["technical", "behavioral", "mixed"];

function orderEntries(data: Record<string, number>): Array<[string, number]> {
  const entries = Object.entries(data).filter(
    ([, n]) => typeof n === "number" && n >= 0,
  );
  return entries.sort((a, b) => {
    const ai = FOCUS_ORDER.indexOf(a[0]);
    const bi = FOCUS_ORDER.indexOf(b[0]);
    if (ai !== -1 || bi !== -1) {
      if (ai === -1) return 1;
      if (bi === -1) return -1;
      return ai - bi;
    }
    return b[1] - a[1];
  });
}

export interface FocusMixProps {
  data: Record<string, number>;
  /** Maps a focus key to a localized label (namespace-agnostic on purpose). */
  labelFor: (key: string) => string;
  /** Copy shown when there is no data / a zero total. */
  emptyLabel: string;
  className?: string;
}

/**
 * Monochrome proportion bars for a focus-area distribution
 * (technical / behavioral / mixed). Deliberately score-free: the visible
 * numbers are session counts, and the bars are a proportional read of the mix,
 * never a grade. The real counts are text (screen-reader friendly); the fill
 * bar itself is decorative (`aria-hidden`).
 */
export function FocusMix({ data, labelFor, emptyLabel, className }: FocusMixProps) {
  const entries = orderEntries(data);
  const total = entries.reduce((sum, [, n]) => sum + n, 0);

  if (total === 0) {
    return (
      <p className={cn("text-sm text-[var(--text-muted)]", className)}>
        {emptyLabel}
      </p>
    );
  }

  const maxValue = Math.max(...entries.map(([, n]) => n));

  return (
    <ul className={cn("space-y-2.5", className)}>
      {entries.map(([key, count]) => {
        const pct = Math.round((count / total) * 100);
        const isMax = count === maxValue && count > 0;
        return (
          <li key={key}>
            <div className="mb-1 flex items-center justify-between gap-3 text-xs">
              <span className="font-medium text-[var(--text-secondary)]">
                {labelFor(key)}
              </span>
              <span className="tabular-nums text-[var(--text-muted)]">
                {count} · {pct}%
              </span>
            </div>
            <div
              aria-hidden
              className="h-2 w-full overflow-hidden rounded-full bg-[var(--bg-muted)]"
            >
              <div
                className={cn(
                  "h-full rounded-full transition-[width] duration-300",
                  isMax
                    ? "bg-[var(--text-primary)]"
                    : "bg-[var(--gray-400)]",
                )}
                style={{ width: `${Math.max(pct, count > 0 ? 3 : 0)}%` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
