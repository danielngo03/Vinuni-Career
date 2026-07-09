"use client";

import { useTranslations } from "next-intl";
import type { Icon } from "@phosphor-icons/react";
import {
  ArrowDown,
  ArrowUp,
  Bell,
  CaretRight,
  IdentificationCard,
  ReadCvLogo,
  Eye,
  Certificate,
  VideoCamera,
  ChatCircle,
  NotePencil,
  Hourglass,
  PlusCircle,
  Gavel,
  Handshake,
  SignIn,
  WarningCircle,
  WifiSlash,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, EmptyState } from "@/components/ui";
import { useUiStore } from "@/stores/ui-store";
import { cn } from "@/lib/utils";
import { ApiError, type DashboardNextAction } from "@/lib/api";
import type { Persona } from "@/stores/auth-store";

/* -------------------------------------------------------------------------- */
/* Guest gate (preserves login intent)                                        */
/* -------------------------------------------------------------------------- */

/**
 * Shown to guests/unauthenticated visitors. Opens the intent-preserving login
 * modal with a returnTo so the user lands back on this dashboard after auth.
 */
export function DashboardGuestGate({ persona }: { persona: Persona }) {
  const tNav = useTranslations("nav");
  const tStates = useTranslations("states");
  const openLoginModal = useUiStore((s) => s.openLoginModal);

  return (
    <EmptyState
      kind="auth"
      icon={SignIn}
      title={tStates("authTitle")}
      description={tStates("authBody")}
      action={
        <Button
          variant="primary"
          size="lg"
          onClick={() =>
            openLoginModal({
              label: tNav("dashboard"),
              returnTo: `/${persona}/dashboard`,
            })
          }
        >
          {tNav("login")}
        </Button>
      }
    />
  );
}

/* -------------------------------------------------------------------------- */
/* Error / offline state                                                      */
/* -------------------------------------------------------------------------- */

export function DashboardErrorState({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry: () => void;
}) {
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const offline = error instanceof ApiError && error.code === "NETWORK_ERROR";

  return (
    <EmptyState
      kind={offline ? "offline" : "error"}
      icon={offline ? WifiSlash : WarningCircle}
      title={offline ? tStates("offlineTitle") : tStates("errorTitle")}
      description={offline ? tStates("offlineBody") : tStates("errorBody")}
      action={
        <Button variant="secondary" onClick={onRetry}>
          {tc("retry")}
        </Button>
      }
    />
  );
}

/* -------------------------------------------------------------------------- */
/* Metric tiles                                                               */
/* -------------------------------------------------------------------------- */

/** Fixed, tokenized icon-chip roles (globals.css .icon-chip-*). Pick by meaning, not decoration. */
export type IconTone = "primary" | "info" | "success" | "warning" | "danger" | "neutral";

const ICON_TONE_CLASS: Record<IconTone, string> = {
  primary: "icon-chip-primary",
  info: "icon-chip-info",
  success: "icon-chip-success",
  warning: "icon-chip-warning",
  danger: "icon-chip-danger",
  neutral: "icon-chip-neutral",
};

export interface MetricItem {
  key: string;
  label: string;
  value: number;
  icon: Icon;
  /** Render value as a percentage (e.g. profile completion). */
  percent?: boolean;
  /** Emphasize when > 0 (work waiting). Uses the warning chip automatically. */
  emphasize?: boolean;
  /** Icon-chip role (DESIGN.md §5.6). Defaults to "primary". Hot/emphasize overrides to "warning". */
  tone?: IconTone;
  /**
   * Optional trend badge shown in the top-right corner of the tile.
   * Direction 'up'/'down' relative to previous period; 'neutral' shows a dash.
   * Color logic: up+normal=teal(good), up+emphasize=amber(more pending=bad),
   * down+normal=red(fewer), down+emphasize=teal(resolved=good).
   */
  trend?: { value: number; direction: "up" | "down" | "neutral" };
  /** If provided the entire tile is a navigable link. */
  href?: string;
  /**
   * Short real-data microcopy shown under the number when the tile is "hot"
   * (emphasize + value > 0) — e.g. "3 tin cần duyệt". Must be derived from
   * the tile's own real value, never a fabricated trend/percentage.
   */
  hotNote?: string;
}

/** Map col counts to literal Tailwind classes so the JIT scanner picks them up. */
const METRIC_GRID_COLS: Record<number, string> = {
  4: "lg:grid-cols-4",
  5: "lg:grid-cols-5",
};

export function MetricTiles({
  items,
  cols = 4,
}: {
  items: MetricItem[];
  cols?: 4 | 5;
}) {
  const colClass = METRIC_GRID_COLS[cols] ?? "lg:grid-cols-4";

  return (
    <dl className={cn("grid grid-cols-2 gap-4 sm:grid-cols-3", colClass)}>
      {items.map((m) => {
        const hot = Boolean(m.emphasize && m.value > 0);

        const cardClass = cn(
          "marketplace-card marketplace-card-hover relative flex flex-col overflow-hidden rounded-[12px] px-4 py-3.5",
          "transition-colors duration-200 bg-[var(--surface-card)]",
          hot && "border-[var(--amber-400)]/70",
        );

        // Trend badge colour logic
        let trendColorClass = "";
        if (m.trend) {
          const { direction } = m.trend;
          const isGood =
            (direction === "up" && !hot) || (direction === "down" && hot);
          const isAmber = direction === "up" && hot;
          if (isGood) {
            trendColorClass =
              "border-[var(--teal-100)] bg-[var(--teal-100)] text-[var(--teal-700)]";
          } else if (isAmber) {
            trendColorClass =
              "border-[var(--amber-100)] bg-[var(--amber-50)] text-[var(--amber-700)]";
          } else if (direction === "neutral") {
            trendColorClass =
              "border-[var(--bg-muted)] bg-[var(--bg-subtle)] text-[var(--text-muted)]";
          } else {
            trendColorClass = "border-[var(--red-100)] bg-[var(--red-50)] text-[var(--red-600)]";
          }
        }

        const inner = (
          <>
            {/* Label row — quiet label left, small tone icon right */}
            <div className="flex items-center justify-between gap-2">
              <dt className="truncate text-[0.8125rem] font-medium text-[var(--text-secondary)]">
                {m.label}
              </dt>
              <span
                className={cn(
                  "flex size-7 shrink-0 items-center justify-center rounded-lg",
                  hot ? ICON_TONE_CLASS.warning : ICON_TONE_CLASS[m.tone ?? "primary"],
                )}
              >
                <m.icon aria-hidden weight="duotone" className="size-4" />
              </span>
            </div>

            {/* Value + trend chip on one baseline */}
            <dd className="mt-1.5 flex items-baseline gap-2">
              <span className="text-[1.75rem] font-bold leading-none tracking-tight tabular-nums text-[var(--text-primary)]">
                {m.percent
                  ? `${m.value}%`
                  : new Intl.NumberFormat().format(m.value)}
              </span>
              {m.trend && (
                <span
                  className={cn(
                    "flex items-center gap-0.5 rounded-full border px-1.5 py-0.5 text-[10px] font-bold leading-none",
                    trendColorClass,
                  )}
                >
                  {m.trend.direction === "up" ? (
                    <ArrowUp aria-hidden weight="bold" className="size-2.5" />
                  ) : m.trend.direction === "down" ? (
                    <ArrowDown aria-hidden weight="bold" className="size-2.5" />
                  ) : null}
                  {m.trend.direction !== "neutral"
                    ? `${m.trend.direction === "up" ? "+" : ""}${m.trend.value}`
                    : "—"}
                </span>
              )}
            </dd>

            {hot && m.hotNote && (
              <p className="mt-1 truncate text-[0.6875rem] font-semibold text-[var(--amber-700)]">
                {m.hotNote}
              </p>
            )}
          </>
        );

        if (m.href) {
          return (
            <Link key={m.key} href={m.href} className={cardClass}>
              {inner}
            </Link>
          );
        }
        return (
          <div key={m.key} className={cardClass}>
            {inner}
          </div>
        );
      })}
    </dl>
  );
}

/* -------------------------------------------------------------------------- */
/* Next-actions rail                                                          */
/* -------------------------------------------------------------------------- */

/**
 * Stable icon per action key across all personas. Labels are localized via the
 * `dashboard.actions.{key}` namespace; an unmapped key falls back to a neutral
 * icon and the raw key is never shown (label has a generic fallback).
 */
const ACTION_ICONS: Record<string, Icon> = {
  // student
  verify_account: IdentificationCard,
  respond_offer: Certificate,
  respond_interview: VideoCamera,
  respond_reveal: Eye,
  unread_messages: ChatCircle,
  build_cv: ReadCvLogo,
  create_alert: Bell,
  // partner
  respond_reveals: Eye,
  jobs_in_draft: NotePencil,
  jobs_pending_review: Hourglass,
  post_job: PlusCircle,
  // university
  review_jobs: Gavel,
  review_partners: Handshake,
};

export function NextActionsRail({
  actions,
  emptyTitle,
  emptyBody,
}: {
  actions: DashboardNextAction[];
  emptyTitle: string;
  emptyBody: string;
}) {
  const t = useTranslations("dashboard.actions");

  if (actions.length === 0) {
    return (
      <div className="rounded-[12px] border border-dashed border-[var(--border-strong)] bg-[var(--surface-card)] px-5 py-6 text-center">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">
          {emptyTitle}
        </h3>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">{emptyBody}</p>
      </div>
    );
  }

  // A real task list, not a lonely tile grid: one bordered container, divided
  // rows, a status dot that reads "pending work" at a glance (v8 "Operations").
  return (
    <QueueList>
      {actions.map((action) => {
        const ActionIcon = ACTION_ICONS[action.key] ?? CaretRight;
        const label = t.has(action.key) ? t(action.key) : action.key;
        const pending = action.count != null && action.count > 0;
        return (
          <li key={action.key}>
            <Link href={action.href} className={cn(QUEUE_ROW_CLASS, "group py-3")}>
              <span
                aria-hidden
                className={cn(
                  "size-1.5 shrink-0 rounded-full",
                  pending ? "bg-[var(--amber-500)]" : "bg-[var(--border-strong)]",
                )}
              />
              <ActionIcon
                aria-hidden
                weight="duotone"
                className="size-[18px] shrink-0 text-[var(--text-muted)]"
              />
              <span className="min-w-0 flex-1 text-[0.8125rem] font-semibold text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]">
                {label}
              </span>
              {pending && (
                <span className="inline-flex min-w-6 items-center justify-center rounded-full bg-[var(--amber-50)] px-2 py-0.5 text-xs font-bold tabular-nums text-[var(--amber-700)]">
                  {action.count}
                </span>
              )}
              <CaretRight
                aria-hidden
                weight="bold"
                className="size-3.5 shrink-0 text-[var(--text-muted)] transition-colors group-hover:text-[var(--brand-primary)]"
              />
            </Link>
          </li>
        );
      })}
    </QueueList>
  );
}

/* -------------------------------------------------------------------------- */
/* Queue list (dense ops rows)                                                */
/* -------------------------------------------------------------------------- */

/**
 * Single bordered container with divided rows — the command-center queue
 * pattern. Replaces floating soft-card lists on partner/university dashboards so
 * the surface reads like a real operations list, not a stack of cards.
 */
export function QueueList({ children }: { children: React.ReactNode }) {
  return (
    <ul className="divide-y divide-[var(--border-default)] overflow-hidden rounded-[12px] border border-[var(--border-default)] bg-[var(--surface-card)]">
      {children}
    </ul>
  );
}

/** Shared flat-row link styling for a QueueList item (no per-row card chrome). */
export const QUEUE_ROW_CLASS =
  "flex items-center justify-between gap-3 px-3.5 py-2.5 outline-none transition-colors hover:bg-[var(--bg-subtle)] focus-visible:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--brand-primary)]/30";

/* -------------------------------------------------------------------------- */
/* Section wrapper                                                            */
/* -------------------------------------------------------------------------- */

export function DashboardSection({
  icon: SectionIcon,
  tone,
  title,
  count,
  action,
  className,
  children,
}: {
  icon: Icon;
  tone?: IconTone;
  title: string;
  count?: number;
  action?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={className}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2.5 text-base font-bold tracking-tight text-[var(--text-primary)]">
          {tone ? (
            <span className={cn("flex size-7 shrink-0 items-center justify-center rounded-lg", ICON_TONE_CLASS[tone])}>
              <SectionIcon aria-hidden weight="duotone" className="size-4" />
            </span>
          ) : (
            <SectionIcon aria-hidden weight="duotone" className="size-5 text-[var(--text-muted)]" />
          )}
          {title}
          {count != null && count > 0 && (
            <span className="inline-flex min-w-5 items-center justify-center rounded-full bg-[var(--bg-muted)] px-1.5 py-0.5 text-xs font-bold tabular-nums text-[var(--text-secondary)]">
              {count}
            </span>
          )}
        </h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export function SectionLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-1 text-sm font-semibold text-[var(--brand-primary)] outline-none hover:underline focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
    >
      {children}
      <CaretRight aria-hidden weight="bold" className="size-4" />
    </Link>
  );
}

/* -------------------------------------------------------------------------- */
/* Loading skeleton (shared shell)                                            */
/* -------------------------------------------------------------------------- */

export function DashboardSkeleton({
  tileCount = 4,
  tileCols = 4,
}: {
  tileCount?: number;
  tileCols?: 4 | 5;
}) {
  const colClass = tileCols === 5 ? "lg:grid-cols-5" : "lg:grid-cols-4";
  return (
    <div className="space-y-8">
      <div
        className={cn(
          "grid grid-cols-2 gap-4 sm:grid-cols-3",
          colClass,
        )}
      >
        {Array.from({ length: tileCount }).map((_, i) => (
          <div
            key={i}
            className="flex items-center gap-3.5 rounded-[12px] border border-[var(--border-default)] bg-[var(--surface-card)] px-4 py-4"
          >
            <div className="animate-skeleton size-11 shrink-0 rounded-xl bg-[var(--bg-muted)]" />
            <div className="min-w-0 flex-1">
              <div className="animate-skeleton h-7 w-12 rounded bg-[var(--bg-muted)]" />
              <div className="animate-skeleton mt-2 h-3 w-20 rounded bg-[var(--bg-muted)]" />
            </div>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {Array.from({ length: 2 }).map((_, i) => (
          <div
            key={i}
            className="animate-skeleton h-[72px] rounded-2xl bg-[var(--bg-muted)]"
          />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="space-y-3">
            <div className="animate-skeleton h-5 w-40 rounded bg-[var(--bg-muted)]" />
            {Array.from({ length: 3 }).map((_, j) => (
              <div
                key={j}
                className="animate-skeleton h-14 rounded-2xl bg-[var(--bg-muted)]"
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
