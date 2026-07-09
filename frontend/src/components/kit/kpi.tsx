import * as React from "react";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { cn } from "@/lib/utils";
import { Sparkline } from "./charts";

/** Delta trend chip on a KPI tile. `direction` describes movement; `good`
 * decides color (up isn't always good — e.g. time-to-hire up is bad). */
export interface KpiDelta {
  value: string;
  direction: "up" | "down" | "flat";
  /** Whether this movement is positive for the business (drives color). */
  good?: boolean;
}

export interface KpiTileProps {
  label: string;
  /** Preformatted display value (already localized). */
  value: string;
  delta?: KpiDelta;
  /** Small trend history for a tile sparkline. */
  spark?: number[];
  sparkColor?: string;
  icon?: React.ElementType;
  /** Deep-link — turns the whole tile into a navigable card. */
  href?: string;
  /** Muted helper under the value (e.g. "3 need review"). */
  hint?: string;
  className?: string;
}

function DeltaChip({ delta }: { delta: KpiDelta }) {
  const good = delta.good ?? delta.direction === "up";
  const Icon = delta.direction === "up" ? TrendingUp : delta.direction === "down" ? TrendingDown : Minus;
  const style: React.CSSProperties =
    delta.direction === "flat"
      ? { background: "var(--bg-muted)", color: "var(--text-muted)" }
      : good
        ? { background: "var(--content-success-soft)", color: "var(--content-success)" }
        : { background: "var(--content-danger-soft)", color: "var(--content-danger)" };
  return (
    <span
      className="inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[0.6875rem] font-semibold tabular-nums"
      style={style}
    >
      <Icon aria-hidden className="size-3" strokeWidth={2.2} />
      {delta.value}
    </span>
  );
}

/**
 * KpiTile — the KPI unit of the v10 system: quiet label, big tabular metric,
 * a trend-delta chip, and an optional tiny sparkline. Icon optional. Wrap in
 * {@link KpiRow} for the standard responsive KPI strip.
 */
export function KpiTile({
  label,
  value,
  delta,
  spark,
  sparkColor,
  icon: Icon,
  href,
  hint,
  className,
}: KpiTileProps) {
  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="type-small truncate font-medium text-muted-foreground">{label}</span>
        {Icon && (
          <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-[var(--bg-muted)] text-muted-foreground">
            <Icon aria-hidden className="size-4" strokeWidth={1.8} />
          </span>
        )}
      </div>
      <div className="mt-2 flex items-end justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="type-metric text-foreground">{value}</span>
            {delta && <DeltaChip delta={delta} />}
          </div>
          {hint && <p className="type-caption mt-1 truncate text-muted-foreground">{hint}</p>}
        </div>
        {spark && spark.length > 1 && (
          <Sparkline data={spark} color={sparkColor} width={72} height={28} className="shrink-0" />
        )}
      </div>
    </>
  );

  const base =
    "block rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-sm)]";
  if (href) {
    return (
      <Link
        href={href}
        className={cn(
          base,
          "outline-none transition-[border-color,box-shadow] hover:border-border-strong hover:shadow-[var(--shadow-md)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]",
          className,
        )}
      >
        {body}
      </Link>
    );
  }
  return <div className={cn(base, className)}>{body}</div>;
}

/** Responsive KPI strip. Pass 3–5 {@link KpiTile}s. */
export function KpiRow({
  children,
  cols = 5,
  className,
}: {
  children: React.ReactNode;
  cols?: 3 | 4 | 5;
  className?: string;
}) {
  const colClass =
    cols === 3
      ? "sm:grid-cols-3"
      : cols === 4
        ? "sm:grid-cols-2 lg:grid-cols-4"
        : "sm:grid-cols-3 lg:grid-cols-5";
  return (
    <div className={cn("grid grid-cols-2 gap-3 sm:gap-4", colClass, className)}>{children}</div>
  );
}

/** StatCard — alias of {@link KpiTile} that always shows its sparkline slot;
 * kept as a distinct name for the design-system contract. */
export function StatCard(props: KpiTileProps) {
  return <KpiTile {...props} />;
}
