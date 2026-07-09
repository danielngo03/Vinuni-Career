import * as React from "react";
import { cn } from "@/lib/utils";
import { type ChipTone } from "./status-chip";

const RAIL_DOT: Record<ChipTone, string> = {
  neutral: "var(--border-strong)",
  success: "var(--content-success)",
  warning: "var(--content-warning)",
  danger: "var(--content-danger)",
  info: "var(--content-info)",
  ai: "var(--content-ai)",
  indigo: "var(--viz-indigo)",
  teal: "var(--viz-teal)",
  amber: "var(--viz-amber)",
  rose: "var(--viz-rose)",
  sky: "var(--viz-sky)",
  emerald: "var(--viz-emerald)",
  violet: "var(--viz-violet)",
  orange: "var(--viz-orange)",
};

export interface ActivityEntry {
  key: string;
  /** Primary line (actor did X). */
  title: React.ReactNode;
  /** Muted secondary line (actor · relative time). */
  meta?: React.ReactNode;
  tone?: ChipTone;
  icon?: React.ElementType;
}

/**
 * ActivityFeed / Timeline — a left-rail timeline of recent events (team
 * activity, audit trail, candidate history). Colored rail dots encode tone;
 * connector line ties the sequence together.
 */
export function ActivityFeed({
  items,
  empty,
  className,
}: {
  items: ActivityEntry[];
  empty?: React.ReactNode;
  className?: string;
}) {
  if (items.length === 0) return <>{empty ?? null}</>;
  return (
    <ul className={cn("relative space-y-4", className)}>
      {items.map((item, i) => {
        const Icon = item.icon;
        const last = i === items.length - 1;
        return (
          <li key={item.key} className="relative flex gap-3">
            {/* rail */}
            <div className="relative flex flex-col items-center">
              <span
                className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full ring-4 ring-[var(--surface-card)]"
                style={{ background: `color-mix(in srgb, ${RAIL_DOT[item.tone ?? "neutral"]} 14%, transparent)` }}
              >
                {Icon ? (
                  <Icon
                    aria-hidden
                    className="size-3.5"
                    strokeWidth={2}
                    style={{ color: RAIL_DOT[item.tone ?? "neutral"] }}
                  />
                ) : (
                  <span className="size-1.5 rounded-full" style={{ background: RAIL_DOT[item.tone ?? "neutral"] }} />
                )}
              </span>
              {!last && <span aria-hidden className="w-px flex-1 bg-border" />}
            </div>
            {/* content */}
            <div className="min-w-0 flex-1 pb-1">
              <div className="text-[0.8125rem] font-medium text-foreground">{item.title}</div>
              {item.meta && <div className="mt-0.5 type-caption text-muted-foreground">{item.meta}</div>}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/** Alias — {@link ActivityFeed} rendered as a generic timeline. */
export const Timeline = ActivityFeed;
