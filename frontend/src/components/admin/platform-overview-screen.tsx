"use client";

import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  CurrencyDollar,
  Warning,
  Users,
  Gavel,
  Robot,
  EnvelopeSimple,
  WarningCircle,
  ShieldWarning,
  ArrowRight,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState, StatusBadge, SkeletonCard } from "@/components/ui";
import { aiOpsApi } from "@/lib/api/ai-ops";
import {
  formatUsd,
  formatErrorRate,
  budgetTone,
} from "./ai-ops-helpers";
import { outboxTone, outboxToneToStatusTone } from "./overview-helpers";
import { cn } from "@/lib/utils";

/* -------------------------------------------------------------------------- */
/* Visibility-gated refetch interval (mirror ai-operations-overview-screen)   */
/* -------------------------------------------------------------------------- */

const OVERVIEW_STALE_TIME = 30_000;
const OVERVIEW_REFETCH = 45_000;

function visibilityGatedInterval(interval: number) {
  return () =>
    typeof document !== "undefined" &&
    document.visibilityState === "visible"
      ? interval
      : false;
}

/* -------------------------------------------------------------------------- */
/* Metric tile (reuses the MetricTile idiom from ai-operations-overview)      */
/* -------------------------------------------------------------------------- */

function OverviewMetricTile({
  label,
  value,
  icon: Icon,
  tone = "primary",
  sub,
}: {
  label: string;
  value: string;
  icon: React.ElementType;
  tone?: "primary" | "warning" | "danger" | "success";
  sub?: string;
}) {
  const chipClass =
    tone === "warning"
      ? "icon-chip-warning"
      : tone === "danger"
        ? "icon-chip-danger"
        : tone === "success"
          ? "icon-chip-success"
          : "icon-chip-primary";

  return (
    <div className="marketplace-card flex flex-col rounded-[12px] px-4 py-3.5">
      <div className="flex items-start justify-between gap-2">
        <span className="truncate text-[0.8125rem] font-medium text-[var(--text-secondary)]">
          {label}
        </span>
        <span
          className={cn(
            "flex size-7 shrink-0 items-center justify-center rounded-lg",
            chipClass,
          )}
        >
          <Icon aria-hidden weight="duotone" className="size-4" />
        </span>
      </div>
      <span
        className="mt-1.5 font-mono text-[1.75rem] font-bold leading-none tracking-tight tabular-nums text-[var(--text-primary)]"
        style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
      >
        {value}
      </span>
      {sub && (
        <span className="mt-1.5 truncate text-[0.6875rem] font-medium text-[var(--text-muted)]">
          {sub}
        </span>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Status band skeleton                                                        */
/* -------------------------------------------------------------------------- */

function StatusBandSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Outbox health row                                                           */
/* -------------------------------------------------------------------------- */

function OutboxHealthRow({
  pending,
  failed,
}: {
  pending: number;
  /** Cumulative failed count from the outbox (backend key: `failed`, not `failed_last_hour`). */
  failed: number;
}) {
  const t = useTranslations("adminConsole.overview.outbox");
  const tone = outboxTone(pending, failed);
  const statusTone = outboxToneToStatusTone(tone);

  const detail =
    failed > 0
      ? t("failed", { count: failed })
      : pending > 0
        ? t("pending", { count: pending })
        : t("healthy");

  return (
    <div className="marketplace-card flex items-center justify-between gap-3 rounded-[12px] px-4 py-3">
      <div className="flex items-center gap-2.5">
        <span
          className={cn(
            "flex size-7 shrink-0 items-center justify-center rounded-lg",
            tone === "rejected"
              ? "icon-chip-danger"
              : tone === "pending"
                ? "icon-chip-warning"
                : "icon-chip-success",
          )}
        >
          <EnvelopeSimple aria-hidden weight="duotone" className="size-4" />
        </span>
        <span className="text-sm font-semibold text-[var(--text-primary)]">
          {t("title")}
        </span>
      </div>
      <StatusBadge tone={statusTone}>{detail}</StatusBadge>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Next-actions rail (admin-specific, deep-links to built sections only)      */
/* -------------------------------------------------------------------------- */

function AdminNextActionsRail({
  moderationPending,
}: {
  moderationPending: number;
}) {
  const t = useTranslations("adminConsole.overview.nextActions");

  const actions: Array<{
    id: string;
    href: string;
    title: string;
    body: string;
    icon: React.ElementType;
    badge?: number;
    tone: "primary" | "warning" | "danger";
  }> = [
    {
      id: "ai-operations",
      href: "/admin/ai-operations",
      title: t("aiOperations"),
      body: t("aiOperationsBody"),
      icon: Robot,
      tone: "primary",
    },
    ...(moderationPending > 0
      ? [
          {
            id: "moderation-queue",
            href: "/university/moderation/jobs",
            title: t("moderationQueue"),
            body: t("moderationQueueBody", { count: moderationPending }),
            icon: Gavel as React.ElementType,
            badge: moderationPending,
            tone: "warning" as const,
          },
        ]
      : []),
  ];

  return (
    <ul
      className="divide-y divide-[var(--border-default)] overflow-hidden rounded-[12px] border border-[var(--border-default)] bg-[var(--surface-card)]"
      role="list"
    >
      {actions.map((action) => {
        const ActionIcon = action.icon;
        const chipClass =
          action.tone === "danger"
            ? "icon-chip-danger"
            : action.tone === "warning"
              ? "icon-chip-warning"
              : "icon-chip-primary";
        return (
          <li key={action.id}>
            <Link
              href={action.href}
              className="group flex items-center gap-3.5 px-4 py-3.5 outline-none transition-colors hover:bg-[var(--bg-subtle)] focus-visible:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--brand-primary)]/30"
            >
              <span
                className={cn(
                  "flex size-8 shrink-0 items-center justify-center rounded-lg",
                  chipClass,
                )}
              >
                <ActionIcon aria-hidden weight="duotone" className="size-4" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]">
                  {action.title}
                </p>
                <p className="mt-0.5 truncate text-xs text-[var(--text-muted)]">
                  {action.body}
                </p>
              </div>
              {action.badge != null && action.badge > 0 && (
                <span className="inline-flex min-w-6 items-center justify-center rounded-full bg-[var(--amber-50)] px-2 py-0.5 text-xs font-bold tabular-nums text-[var(--amber-700)]">
                  {action.badge}
                </span>
              )}
              <ArrowRight
                aria-hidden
                weight="bold"
                className="size-4 shrink-0 text-[var(--text-muted)] transition-colors group-hover:text-[var(--brand-primary)]"
              />
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

/* -------------------------------------------------------------------------- */
/* Incidents strip (future phase — EmptyState placeholder)                    */
/* -------------------------------------------------------------------------- */

function IncidentsStrip() {
  const t = useTranslations("adminConsole.overview.incidents");

  return (
    <section aria-labelledby="admin-incidents-title">
      <h2
        id="admin-incidents-title"
        className="mb-3 text-base font-bold tracking-tight text-[var(--text-primary)]"
      >
        {t("title")}
      </h2>
      <EmptyState
        kind="empty"
        icon={ShieldWarning}
        title={t("emptyTitle")}
        description={t("emptyBody")}
        className="rounded-[12px] border border-dashed border-[var(--border-default)] bg-[var(--surface-card)] py-8"
      />
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/* Main screen                                                                 */
/* -------------------------------------------------------------------------- */

export function PlatformOverviewScreen() {
  const t = useTranslations("adminConsole.overview");
  const tPage = useTranslations("adminConsole.page");

  const query = useQuery({
    queryKey: ["admin", "overview"] as const,
    queryFn: () => aiOpsApi.platformOverview(),
    staleTime: OVERVIEW_STALE_TIME,
    refetchInterval: visibilityGatedInterval(OVERVIEW_REFETCH),
    retry: 1,
  });

  const renderStatusBand = () => {
    if (query.isPending) {
      return <StatusBandSkeleton />;
    }

    if (query.isError) {
      return (
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("errorTitle")}
          description={t("errorBody")}
          action={
            <button
              type="button"
              onClick={() => void query.refetch()}
              className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
            >
              {t("retry")}
            </button>
          }
        />
      );
    }

    const data = query.data;
    // spend_today and budget are numbers from the real backend (not strings)
    const aiSpend = data.ai.spend_today ?? 0;
    const aiErrorRate = data.ai.error_rate ?? 0;
    const aiRequests = data.ai.requests ?? 0;
    const moderationPending = data.moderation_pending ?? 0;
    const activeUsers = data.active_users ?? 0;
    const outboxPending = data.outbox.pending ?? 0;
    // The backend returns `failed` (cumulative), not `failed_last_hour`
    const outboxFailed = data.outbox.failed ?? 0;

    // Determine tile tones (no per-day budget on platform overview — default teal)
    const spendToneRaw = budgetTone(aiSpend, 0);
    const spendTile =
      spendToneRaw === "red"
        ? "danger"
        : spendToneRaw === "amber"
          ? "warning"
          : "primary";
    const errorRateTone =
      aiErrorRate > 0.05
        ? "danger"
        : aiErrorRate > 0.01
          ? "warning"
          : "success";
    const moderationTone = moderationPending > 0 ? "warning" : "success";

    return (
      <div className="space-y-4">
        {/* Metric tiles — 4-col */}
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <OverviewMetricTile
            label={t("metric.aiSpend")}
            value={formatUsd(aiSpend)}
            icon={CurrencyDollar}
            tone={spendTile}
            sub={`${new Intl.NumberFormat().format(aiRequests)} ${t("metric.aiRequestsSuffix")}`}
          />
          <OverviewMetricTile
            label={t("metric.aiErrorRate")}
            value={formatErrorRate(aiErrorRate)}
            icon={Warning}
            tone={errorRateTone}
          />
          <OverviewMetricTile
            label={t("metric.moderationPending")}
            value={new Intl.NumberFormat().format(moderationPending)}
            icon={Gavel}
            tone={moderationTone}
          />
          <OverviewMetricTile
            label={t("metric.activeUsers")}
            value={new Intl.NumberFormat().format(activeUsers)}
            icon={Users}
            tone="primary"
          />
        </div>

        {/* Outbox health */}
        <OutboxHealthRow
          pending={outboxPending}
          failed={outboxFailed}
        />
      </div>
    );
  };

  const renderNextActions = () => {
    if (query.isPending || query.isError) return null;
    const moderationPending = query.data.moderation_pending ?? 0;
    return (
      <section aria-labelledby="admin-next-actions-title">
        <h2
          id="admin-next-actions-title"
          className="mb-3 text-base font-bold tracking-tight text-[var(--text-primary)]"
        >
          {t("nextActions.title")}
        </h2>
        <AdminNextActionsRail moderationPending={moderationPending} />
      </section>
    );
  };

  return (
    <>
      <PageHeader
        title={tPage("overviewTitle")}
      />

      <div className="space-y-8">
        {/* System status band */}
        <section aria-labelledby="admin-status-band-title">
          <h2
            id="admin-status-band-title"
            className="mb-3 text-base font-bold tracking-tight text-[var(--text-primary)]"
          >
            {t("statusBandTitle")}
          </h2>
          {renderStatusBand()}
        </section>

        {/* Next-actions rail (only shown when data is available) */}
        {renderNextActions()}

        {/* Incidents strip — future phase placeholder */}
        <IncidentsStrip />
      </div>
    </>
  );
}
