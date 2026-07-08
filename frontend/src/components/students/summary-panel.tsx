import { ChartBar } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

/**
 * Honest, deterministic "Summary" panel shared by the student operating surfaces
 * (applications / saved jobs / job alerts / my events).
 *
 * It replaces the four copy-pasted "AI Insights" banners: the content is a small
 * set of client-derived observations from data the screen already loaded, so it
 * is labelled "Summary" / "Tổng quan" — never "AI" (there is no model/backend
 * recommendation contract behind it, and `docs/UI_QUALITY_BAR.md` forbids "AI" /
 * "recommended" framing without one). Flat `marketplace-card` treatment per
 * `docs/DESIGN.md` §1.1.1 (glass is reserved for topbar + slide-in panels).
 */
export function SummaryPanel({
  title,
  items,
  className,
}: {
  title: string;
  /** Already-resolved observation lines (each screen derives its own copy). */
  items: React.ReactNode[];
  className?: string;
}) {
  if (items.length === 0) return null;

  return (
    <section
      className={cn("marketplace-card rounded-[12px] p-4", className)}
      aria-label={title}
    >
      <h2 className="mb-2.5 flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
        <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-neutral">
          <ChartBar aria-hidden weight="duotone" className="size-3.5" />
        </span>
        {title}
      </h2>
      <ul className="space-y-1.5">
        {items.map((item, i) => (
          <li
            key={i}
            className="flex items-start gap-2 text-xs text-[var(--text-secondary)]"
          >
            <span
              aria-hidden
              className="mt-[7px] size-1 shrink-0 rounded-full bg-[var(--text-muted)]"
            />
            <span className="min-w-0">{item}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
