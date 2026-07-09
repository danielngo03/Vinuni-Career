import * as React from "react";
import { ChevronRight } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { cn } from "@/lib/utils";
import { type ChipTone } from "./status-chip";

const DOT: Record<ChipTone, string> = {
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

export interface AttentionItem {
  key: string;
  label: string;
  href: string;
  /** Dot color — encodes urgency/priority. */
  tone?: ChipTone;
  /** Count badge (omit/null to hide). */
  count?: number | null;
  /** Right-side muted meta (e.g. priority label, age). */
  meta?: string;
  icon?: React.ElementType;
}

/**
 * AttentionPanel — the ranked "what needs your attention" queue: a bordered
 * list of colored-dot rows that deep-link into the real workflow. This is the
 * command-center primitive every persona surface uses for its next-action queue.
 */
export function AttentionPanel({
  items,
  empty,
  className,
}: {
  items: AttentionItem[];
  /** Rendered when there is nothing to act on. */
  empty?: React.ReactNode;
  className?: string;
}) {
  if (items.length === 0) {
    return <>{empty ?? null}</>;
  }
  return (
    <ul
      className={cn(
        "divide-y divide-border overflow-hidden rounded-xl border border-border bg-card",
        className,
      )}
    >
      {items.map((item) => {
        const Icon = item.icon;
        const hasCount = item.count != null && item.count > 0;
        return (
          <li key={item.key}>
            <Link
              href={item.href}
              className="group flex items-center gap-3 px-4 py-3 outline-none transition-colors hover:bg-[var(--bg-subtle)] focus-visible:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--field-focus-border)]"
            >
              <span
                aria-hidden
                className="size-2 shrink-0 rounded-full"
                style={{ background: DOT[item.tone ?? "neutral"] }}
              />
              {Icon && (
                <Icon aria-hidden className="size-[18px] shrink-0 text-muted-foreground" strokeWidth={1.8} />
              )}
              <span className="min-w-0 flex-1 truncate text-[0.8125rem] font-semibold text-foreground group-hover:text-[var(--brand-primary)]">
                {item.label}
              </span>
              {item.meta && (
                <span className="shrink-0 text-[0.6875rem] font-medium uppercase tracking-wide text-muted-foreground">
                  {item.meta}
                </span>
              )}
              {hasCount && (
                <span
                  className="inline-flex min-w-6 shrink-0 items-center justify-center rounded-full px-2 py-0.5 text-xs font-bold tabular-nums"
                  style={{ background: "var(--content-warning-soft)", color: "var(--content-warning)" }}
                >
                  {item.count}
                </span>
              )}
              <ChevronRight
                aria-hidden
                strokeWidth={2}
                className="size-3.5 shrink-0 text-muted-foreground transition-colors group-hover:text-[var(--brand-primary)]"
              />
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
