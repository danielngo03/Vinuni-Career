"use client";

import { cn } from "@/lib/utils";

export type InsightTone = "neutral" | "success" | "warning" | "danger";

export interface InsightItem {
  label: React.ReactNode;
  tone?: InsightTone;
}

export interface InsightPanelProps {
  /** Honest section title — "Signals" / "Highlights", NOT "AI" unless the
   *  content is a real model output with confirmation. */
  title: string;
  items: InsightItem[];
  icon?: React.ReactNode;
  className?: string;
}

const TONE_DOT: Record<InsightTone, string> = {
  neutral: "bg-[var(--text-muted)]",
  success: "bg-[var(--color-success)]",
  warning: "bg-[var(--color-warning)]",
  danger: "bg-[var(--color-error)]",
};

/**
 * Flat, monochrome panel for derived "signals"/highlights. Replaces the soft
 * `bg-gradient-to-br from-[var(--ai-accent-soft)]` "AI insight" cards that
 * violated the no-gradient bar AND mislabeled client-side heuristics as AI.
 * Reserve an actual AI treatment for real, confirmed model output.
 */
export function InsightPanel({ title, items, icon, className }: InsightPanelProps) {
  if (items.length === 0) return null;
  return (
    <section
      aria-label={title}
      className={cn(
        "rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-4 shadow-[var(--shadow-xs)]",
        className,
      )}
    >
      <div className="mb-2.5 flex items-center gap-2">
        {icon && (
          <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-neutral">
            {icon}
          </span>
        )}
        <h3 className="text-sm font-bold text-[var(--text-primary)]">{title}</h3>
      </div>
      <ul className="space-y-1.5">
        {items.map((item, i) => (
          <li
            key={i}
            className="flex items-start gap-2 text-sm leading-snug text-[var(--text-secondary)]"
          >
            <span
              aria-hidden
              className={cn(
                "mt-[0.4rem] size-1.5 shrink-0 rounded-full",
                TONE_DOT[item.tone ?? "neutral"],
              )}
            />
            <span className="min-w-0">{item.label}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
