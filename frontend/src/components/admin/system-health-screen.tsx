"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  HardDrive,
  Queue,
  Pulse,
  CheckCircle,
  XCircle,
  WarningCircle,
  CircleDashed,
  Timer,
  CheckSquare,
  ArrowClockwise,
  Database,
  ShareNetwork,
} from "@phosphor-icons/react";
import { PageHeader } from "@/components/layout/page-header";
import {
  Tabs,
  TabPanel,
  StatusBadge,
  Skeleton,
  SkeletonCard,
  EmptyState,
  DataTable,
} from "@/components/ui";
import type { StatusTone } from "@/components/ui";
import type { Column } from "@/components/ui/data-table";
import {
  systemHealthApi,
  type JobHealth,
  type OutboxHealth,
} from "@/lib/api/system-health";
import { formatLatency } from "./ai-ops-helpers";
import { SystemHealthFlow } from "./system-health-flow";
import { SystemHealthTopology } from "./system-health-topology";
import { cn } from "@/lib/utils";

/* -------------------------------------------------------------------------- */
/* Visibility-gated refetch interval helper (Tier-A: 10s)                     */
/* -------------------------------------------------------------------------- */

const REFETCH_INTERVAL = 10_000;

function visibilityGatedInterval(interval: number) {
  return () =>
    typeof document !== "undefined" &&
    document.visibilityState === "visible"
      ? interval
      : false;
}

/* -------------------------------------------------------------------------- */
/* Interval formatter: seconds → human readable                               */
/* -------------------------------------------------------------------------- */

function formatInterval(seconds: number): string {
  if (!isFinite(seconds) || seconds <= 0) return `${seconds}s`;
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

/* -------------------------------------------------------------------------- */
/* Relative time formatter                                                     */
/* -------------------------------------------------------------------------- */

function formatRelativeTime(isoString: string | null): string {
  if (!isoString) return "—";
  const date = new Date(isoString);
  if (isNaN(date.getTime())) return "—";
  const diffMs = Date.now() - date.getTime();
  const diffSec = Math.round(diffMs / 1000);
  if (diffSec < 0) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.round(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.round(diffSec / 3600)}h ago`;
  return `${Math.round(diffSec / 86400)}d ago`;
}

/* -------------------------------------------------------------------------- */
/* Service readiness tile                                                      */
/* -------------------------------------------------------------------------- */

function ReadinessTile({
  label,
  status,
  icon: Icon,
}: {
  label: string;
  status: "ok" | "down";
  icon: React.ElementType;
}) {
  const tone: StatusTone = status === "ok" ? "active" : "rejected";
  const chipClass =
    status === "ok" ? "icon-chip-success" : "icon-chip-danger";

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
      <div className="mt-2">
        <StatusBadge tone={tone}>
          {status === "ok" ? (
            <CheckCircle aria-hidden weight="fill" className="size-3 shrink-0" />
          ) : (
            <XCircle aria-hidden weight="fill" className="size-3 shrink-0" />
          )}
          {status.toUpperCase()}
        </StatusBadge>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Generic metric tile                                                         */
/* -------------------------------------------------------------------------- */

function MetricTile({
  label,
  value,
  icon: Icon,
  tone = "primary",
}: {
  label: string;
  value: string | React.ReactNode;
  icon: React.ElementType;
  tone?: "primary" | "warning" | "danger" | "success";
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
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Panel wrapper                                                              */
/* -------------------------------------------------------------------------- */

function PanelCard({
  title,
  icon: Icon,
  children,
  className,
}: {
  title: string;
  icon: React.ElementType;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      aria-labelledby={`sh-panel-${title.toLowerCase().replace(/\s+/g, "-")}`}
      className={cn("marketplace-card rounded-[12px] p-5", className)}
    >
      <h2
        id={`sh-panel-${title.toLowerCase().replace(/\s+/g, "-")}`}
        className="mb-4 flex items-center gap-2 text-sm font-bold tracking-tight text-[var(--text-primary)]"
      >
        <span className="icon-chip-primary flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm">
          <Icon aria-hidden weight="duotone" className="size-4" />
        </span>
        {title}
      </h2>
      {children}
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/* Outbox health card (pure display — receives data from parent)              */
/* -------------------------------------------------------------------------- */

function OutboxHealthCardContent({
  outbox,
  tServices,
  tOutbox,
}: {
  outbox: OutboxHealth;
  tServices: ReturnType<typeof useTranslations>;
  tOutbox: ReturnType<typeof useTranslations>;
}) {
  const hasFailure = (outbox.failed ?? 0) > 0 || (outbox.dead ?? 0) > 0;
  const hasPending = (outbox.pending ?? 0) > 0;
  const outboxTone: StatusTone = hasFailure
    ? "rejected"
    : hasPending
      ? "pending"
      : "active";

  const outboxLabel = hasFailure
    ? tOutbox("failed")
    : hasPending
      ? tOutbox("pending")
      : tServices("healthy");

  const rows: Array<{ key: string; label: string; value: string | number }> = [
    { key: "pending", label: tOutbox("pending"), value: outbox.pending ?? 0 },
    { key: "sent", label: tOutbox("sent"), value: outbox.sent ?? 0 },
    { key: "failed", label: tOutbox("failed"), value: outbox.failed ?? 0 },
    { key: "skipped", label: tOutbox("skipped"), value: outbox.skipped ?? 0 },
    { key: "dead", label: tOutbox("dead"), value: outbox.dead ?? 0 },
    {
      key: "retry_scheduled",
      label: tOutbox("retryScheduled"),
      value: outbox.retry_scheduled ?? 0,
    },
    {
      key: "oldest_pending_age",
      label: tOutbox("oldestPendingAge"),
      value:
        outbox.oldest_pending_age_seconds != null
          ? `${outbox.oldest_pending_age_seconds}s`
          : "—",
    },
  ];

  const cardBorder = hasFailure
    ? "border-[var(--red-400)]/50"
    : hasPending
      ? "border-[var(--amber-400)]/50"
      : "border-[var(--teal-500)]/30";

  const cardBg = hasFailure
    ? "bg-[var(--red-50)]/60"
    : hasPending
      ? "bg-[var(--amber-50)]/60"
      : "bg-[var(--teal-50)]/40";

  return (
    <div
      className={cn(
        "rounded-xl border p-4",
        cardBorder,
        cardBg,
      )}
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <span className="text-sm font-bold tracking-tight text-[var(--text-primary)]">
          {tServices("outboxTitle")}
        </span>
        <StatusBadge tone={outboxTone}>{outboxLabel}</StatusBadge>
      </div>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3 lg:grid-cols-4">
        {rows.map(({ key, label, value }) => {
          const isHighlighted =
            (key === "failed" && (outbox.failed ?? 0) > 0) ||
            (key === "dead" && (outbox.dead ?? 0) > 0);

          return (
            <div key={key} className="flex flex-col gap-0.5">
              <dt className="text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                {label}
              </dt>
              <dd
                className={cn(
                  "font-mono text-sm font-bold tabular-nums",
                  isHighlighted
                    ? "text-[var(--brand-red)]"
                    : "text-[var(--text-primary)]",
                )}
                style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
              >
                {value}
              </dd>
            </div>
          );
        })}
      </dl>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Services tab                                                                */
/* -------------------------------------------------------------------------- */

function ServicesTab() {
  // All hooks at the top — no conditional hook calls
  const t = useTranslations("adminConsole.systemHealth.services");
  const tOutbox = useTranslations("adminConsole.systemHealth.services.outbox");
  const tRetry = useTranslations("adminConsole.systemHealth");

  const query = useQuery({
    queryKey: ["system-health", "services"] as const,
    queryFn: () => systemHealthApi.services(),
    staleTime: 8_000,
    refetchInterval: visibilityGatedInterval(REFETCH_INTERVAL),
    retry: 1,
  });

  if (query.isPending) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <SkeletonCard />
          <SkeletonCard />
        </div>
        <Skeleton className="h-40 w-full" />
      </div>
    );
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
            onClick={() => void query.refetch()}
            className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
          >
            {tRetry("retry")}
          </button>
        }
      />
    );
  }

  const data = query.data;

  return (
    <div className="space-y-6">
      {/* Readiness tiles */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        <ReadinessTile
          label={t("dbTileLabel")}
          status={data.database}
          icon={Database}
        />
        <ReadinessTile
          label={t("redisTileLabel")}
          status={data.redis}
          icon={HardDrive}
        />
      </div>

      {/* Outbox health card (pure display, data from query above) */}
      <OutboxHealthCardContent
        outbox={data.outbox}
        tServices={t}
        tOutbox={tOutbox}
      />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Job status badge                                                            */
/* -------------------------------------------------------------------------- */

function JobStatusBadge({
  status,
  neverRun,
  tNeverRun,
  tOk,
  tError,
}: {
  status: "ok" | "error" | null;
  neverRun: boolean;
  tNeverRun: string;
  tOk: string;
  tError: string;
}) {
  if (neverRun || status === null) {
    return (
      <StatusBadge tone="draft">
        <CircleDashed aria-hidden weight="bold" className="size-3 shrink-0" />
        {tNeverRun}
      </StatusBadge>
    );
  }
  if (status === "ok") {
    return (
      <StatusBadge tone="active">
        <CheckCircle aria-hidden weight="fill" className="size-3 shrink-0" />
        {tOk}
      </StatusBadge>
    );
  }
  return (
    <StatusBadge tone="rejected">
      <XCircle aria-hidden weight="fill" className="size-3 shrink-0" />
      {tError}
    </StatusBadge>
  );
}

/* -------------------------------------------------------------------------- */
/* Job status matrix — compact grid colored by health                         */
/* -------------------------------------------------------------------------- */

function JobStatusMatrix({ jobs }: { jobs: JobHealth[] }) {
  const t = useTranslations("adminConsole.systemHealth.jobMatrix");
  const tStatus = useTranslations("adminConsole.systemHealth.status");
  const tQueuesJobs = useTranslations("adminConsole.systemHealth.queuesJobs");

  if (jobs.length === 0) {
    return (
      <p className="text-sm text-[var(--text-muted)]">{tQueuesJobs("emptyTitle")}</p>
    );
  }

  return (
    <div
      className="grid gap-2"
      style={{
        gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
      }}
      role="list"
      aria-label={t("ariaLabel")}
    >
      {jobs.map((job) => {
        const isError = job.last_status === "error";
        const isNeverRun = job.never_run || job.last_status === null;
        const isOk = job.last_status === "ok";

        const borderColor = isError
          ? "var(--red-600)"
          : isNeverRun
            ? "var(--border-strong)"
            : "var(--teal-500)";

        const bgColor = isError
          ? "var(--red-50)"
          : isNeverRun
            ? "var(--bg-muted)"
            : "var(--teal-50)";

        const dotColor = isError
          ? "var(--red-600)"
          : isNeverRun
            ? "var(--text-muted)"
            : "var(--teal-600)";

        const statusText = isError
          ? tStatus("error")
          : isNeverRun
            ? tStatus("neverRun")
            : tStatus("ok");

        const lastRun = formatRelativeTime(job.last_finished_at);
        const duration =
          job.last_duration_ms !== null ? formatLatency(job.last_duration_ms) : null;

        // Last result as tooltip content — truncated for display
        const resultSummary: string | null = (() => {
          if (!job.last_result) return null;
          try {
            return JSON.stringify(job.last_result).slice(0, 120);
          } catch {
            return null;
          }
        })();

        return (
          <div
            key={job.name}
            role="listitem"
            title={resultSummary ?? statusText}
            className="group relative flex flex-col gap-1.5 rounded-lg border p-3 transition-shadow hover:shadow-sm"
            style={{
              borderColor,
              background: bgColor,
              borderWidth: "1.5px",
            }}
          >
            {/* Status dot + name */}
            <div className="flex items-center gap-2">
              <span
                className="size-2.5 shrink-0 rounded-full"
                style={{ background: dotColor }}
                aria-hidden
              />
              <span
                className="truncate font-mono text-[0.7rem] font-bold text-[var(--text-primary)]"
                style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
                title={job.name}
              >
                {job.name}
              </span>
            </div>

            {/* Status badge row */}
            <div className="flex items-center gap-1.5">
              {isError ? (
                <XCircle
                  aria-hidden
                  weight="fill"
                  className="size-3 shrink-0"
                  style={{ color: "var(--red-600)" }}
                />
              ) : isOk ? (
                <CheckCircle
                  aria-hidden
                  weight="fill"
                  className="size-3 shrink-0"
                  style={{ color: "var(--teal-600)" }}
                />
              ) : (
                <CircleDashed
                  aria-hidden
                  weight="bold"
                  className="size-3 shrink-0"
                  style={{ color: "var(--text-muted)" }}
                />
              )}
              <span
                className="text-[0.6875rem] font-semibold"
                style={{
                  color: isError
                    ? "var(--red-600)"
                    : isNeverRun
                      ? "var(--text-muted)"
                      : "var(--teal-700)",
                }}
              >
                {statusText}
              </span>
            </div>

            {/* Meta: last run + duration */}
            <div className="flex items-center justify-between gap-1 text-[0.65rem] text-[var(--text-muted)]">
              <span>{isNeverRun ? t("neverRun") : lastRun}</span>
              {duration && !isNeverRun && (
                <span
                  className="font-mono tabular-nums"
                  style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
                >
                  {duration}
                </span>
              )}
            </div>

            {/* Interval badge */}
            <div className="text-[0.6rem] text-[var(--text-muted)]">
              {t("interval", { interval: formatInterval(job.interval_seconds) })}
            </div>

            {/* Hover tooltip for last_result */}
            {resultSummary && (
              <div
                className={cn(
                  "pointer-events-none absolute bottom-full left-0 z-20 mb-1.5 hidden w-64 rounded-lg border p-2 text-[0.65rem] shadow-md group-hover:block",
                )}
                style={{
                  background: "var(--surface-card)",
                  borderColor: "var(--border-default)",
                  color: "var(--text-secondary)",
                  fontFamily: "'JetBrains Mono', ui-monospace, monospace",
                  wordBreak: "break-all",
                }}
                aria-hidden
              >
                {resultSummary}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Queues & Jobs tab                                                           */
/* -------------------------------------------------------------------------- */

function QueuesJobsTab() {
  const t = useTranslations("adminConsole.systemHealth.queuesJobs");
  const tStatus = useTranslations("adminConsole.systemHealth.status");
  const tRetry = useTranslations("adminConsole.systemHealth");
  const tMatrix = useTranslations("adminConsole.systemHealth.jobMatrix");

  const queuesQuery = useQuery({
    queryKey: ["system-health", "queues"] as const,
    queryFn: () => systemHealthApi.queues(),
    staleTime: 8_000,
    refetchInterval: visibilityGatedInterval(REFETCH_INTERVAL),
    retry: 1,
  });

  const jobsQuery = useQuery({
    queryKey: ["system-health", "jobs"] as const,
    queryFn: () => systemHealthApi.jobs(),
    staleTime: 8_000,
    refetchInterval: visibilityGatedInterval(REFETCH_INTERVAL),
    retry: 1,
  });

  /* ---------------------------------------------------------------------- */
  /* Queue tiles                                                             */
  /* ---------------------------------------------------------------------- */

  const renderQueueTiles = () => {
    if (queuesQuery.isPending) {
      return (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      );
    }

    if (queuesQuery.isError) {
      return (
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("errorTitle")}
          description={t("errorBody")}
          action={
            <button
              onClick={() => void queuesQuery.refetch()}
              className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
            >
              {tRetry("retry")}
            </button>
          }
        />
      );
    }

    const q = queuesQuery.data;
    const redisTone: "success" | "danger" =
      q.redis === "ok" ? "success" : "danger";
    const depthRaw = q.celery_default_queue_depth;
    const depthDisplay = depthRaw !== null ? String(depthRaw) : t("na");
    const brokerDisplay = q.broker_configured ? t("yes") : t("no");
    const brokerTone: "success" | "danger" = q.broker_configured
      ? "success"
      : "danger";

    return (
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        {/* Redis status */}
        <div className="marketplace-card flex flex-col rounded-[12px] px-4 py-3.5">
          <div className="flex items-start justify-between gap-2">
            <span className="truncate text-[0.8125rem] font-medium text-[var(--text-secondary)]">
              {t("redisTileLabel")}
            </span>
            <span
              className={cn(
                "flex size-7 shrink-0 items-center justify-center rounded-lg",
                q.redis === "ok" ? "icon-chip-success" : "icon-chip-danger",
              )}
            >
              <HardDrive aria-hidden weight="duotone" className="size-4" />
            </span>
          </div>
          <div className="mt-2">
            <StatusBadge
              tone={redisTone === "success" ? "active" : "rejected"}
            >
              {q.redis === "ok" ? (
                <CheckCircle aria-hidden weight="fill" className="size-3 shrink-0" />
              ) : (
                <XCircle aria-hidden weight="fill" className="size-3 shrink-0" />
              )}
              {tStatus(q.redis)}
            </StatusBadge>
          </div>
        </div>

        {/* Queue depth */}
        <MetricTile
          label={t("queueDepthTileLabel")}
          value={depthDisplay}
          icon={Queue}
          tone="primary"
        />

        {/* Broker configured */}
        <div className="marketplace-card flex flex-col rounded-[12px] px-4 py-3.5">
          <div className="flex items-start justify-between gap-2">
            <span className="truncate text-[0.8125rem] font-medium text-[var(--text-secondary)]">
              {t("brokerConfiguredTileLabel")}
            </span>
            <span
              className={cn(
                "flex size-7 shrink-0 items-center justify-center rounded-lg",
                q.broker_configured ? "icon-chip-success" : "icon-chip-danger",
              )}
            >
              <CheckSquare aria-hidden weight="duotone" className="size-4" />
            </span>
          </div>
          <div className="mt-2">
            <StatusBadge
              tone={brokerTone === "success" ? "active" : "rejected"}
            >
              {brokerDisplay}
            </StatusBadge>
          </div>
        </div>
      </div>
    );
  };

  /* ---------------------------------------------------------------------- */
  /* Jobs table                                                              */
  /* ---------------------------------------------------------------------- */

  const renderJobsTable = () => {
    if (jobsQuery.isPending) {
      return (
        <PanelCard title={t("jobsTableCaption")} icon={Timer}>
          <Skeleton className="h-48 w-full" />
        </PanelCard>
      );
    }

    if (jobsQuery.isError) {
      return (
        <PanelCard title={t("jobsTableCaption")} icon={Timer}>
          <EmptyState
            kind="error"
            icon={WarningCircle}
            title={t("errorTitle")}
            description={t("errorBody")}
            action={
              <button
                onClick={() => void jobsQuery.refetch()}
                className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
              >
                {tRetry("retry")}
              </button>
            }
          />
        </PanelCard>
      );
    }

    const rawJobs = jobsQuery.data.jobs ?? [];

    // Sort: errors and never-run near top, then by name
    const sortedJobs = [...rawJobs].sort((a, b) => {
      const aScore =
        a.last_status === "error" ? 0 : a.never_run || !a.last_status ? 1 : 2;
      const bScore =
        b.last_status === "error" ? 0 : b.never_run || !b.last_status ? 1 : 2;
      if (aScore !== bScore) return aScore - bScore;
      return a.name.localeCompare(b.name);
    });

    const columns: Column<JobHealth>[] = [
      {
        key: "name",
        header: t("col.name"),
        cell: (row) => (
          <span
            className="font-mono text-xs font-semibold text-[var(--text-primary)]"
            style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
          >
            {row.name}
          </span>
        ),
      },
      {
        key: "interval_seconds",
        header: t("col.interval"),
        cell: (row) => (
          <span
            className="font-mono text-xs tabular-nums text-[var(--text-secondary)]"
            style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
          >
            {formatInterval(row.interval_seconds)}
          </span>
        ),
      },
      {
        key: "last_finished_at",
        header: t("col.lastRun"),
        cell: (row) => {
          if (row.never_run || !row.last_finished_at) {
            return (
              <span className="text-xs text-[var(--text-muted)]">
                {t("dash")}
              </span>
            );
          }
          return (
            <span className="text-xs text-[var(--text-secondary)]">
              {formatRelativeTime(row.last_finished_at)}
            </span>
          );
        },
      },
      {
        key: "last_duration_ms",
        header: t("col.duration"),
        align: "right",
        cell: (row) => {
          if (row.last_duration_ms === null) {
            return (
              <span className="font-mono text-xs text-[var(--text-muted)]">
                {t("dash")}
              </span>
            );
          }
          return (
            <span
              className="font-mono text-xs tabular-nums text-[var(--text-secondary)]"
              style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
            >
              {formatLatency(row.last_duration_ms)}
            </span>
          );
        },
      },
      {
        key: "last_status",
        header: t("col.status"),
        cell: (row) => (
          <JobStatusBadge
            status={row.last_status}
            neverRun={row.never_run}
            tNeverRun={t("neverRun")}
            tOk={tStatus("ok")}
            tError={tStatus("error")}
          />
        ),
      },
    ];

    return (
      <div className="space-y-5">
        {/* Job status matrix — compact at-a-glance grid */}
        <PanelCard title={tMatrix("panelTitle")} icon={ShareNetwork}>
          <JobStatusMatrix jobs={sortedJobs} />
        </PanelCard>

        {/* Full data table */}
        <PanelCard title={t("jobsTableCaption")} icon={Timer}>
          <DataTable<JobHealth>
            columns={columns}
            rows={sortedJobs}
            getRowId={(row) => row.name}
            caption={t("jobsTableCaption")}
            empty={{
              kind: "empty",
              icon: Pulse,
              title: t("emptyTitle"),
              description: t("emptyBody"),
            }}
          />
        </PanelCard>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {renderQueueTiles()}
      {renderJobsTable()}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Overview / Sơ đồ tab — pipeline flow + service topology                    */
/* -------------------------------------------------------------------------- */

function OverviewTab() {
  const t = useTranslations("adminConsole.systemHealth.overview");
  const tRetry = useTranslations("adminConsole.systemHealth");

  const jobsQuery = useQuery({
    queryKey: ["system-health", "jobs"] as const,
    queryFn: () => systemHealthApi.jobs(),
    staleTime: 8_000,
    refetchInterval: visibilityGatedInterval(REFETCH_INTERVAL),
    retry: 1,
  });

  const queuesQuery = useQuery({
    queryKey: ["system-health", "queues"] as const,
    queryFn: () => systemHealthApi.queues(),
    staleTime: 8_000,
    refetchInterval: visibilityGatedInterval(REFETCH_INTERVAL),
    retry: 1,
  });

  const servicesQuery = useQuery({
    queryKey: ["system-health", "services"] as const,
    queryFn: () => systemHealthApi.services(),
    staleTime: 8_000,
    refetchInterval: visibilityGatedInterval(REFETCH_INTERVAL),
    retry: 1,
  });

  const isLoading =
    jobsQuery.isPending || queuesQuery.isPending || servicesQuery.isPending;
  const isError =
    jobsQuery.isError && queuesQuery.isError && servicesQuery.isError;

  if (isError) {
    return (
      <EmptyState
        kind="error"
        icon={WarningCircle}
        title={t("errorTitle")}
        description={t("errorBody")}
        action={
          <button
            onClick={() => {
              void jobsQuery.refetch();
              void queuesQuery.refetch();
              void servicesQuery.refetch();
            }}
            className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
          >
            {tRetry("retry")}
          </button>
        }
      />
    );
  }

  const outbox = servicesQuery.data?.outbox;

  return (
    <div className="space-y-6">
      {/* Pipeline flow diagram */}
      <section
        aria-labelledby="sh-overview-flow"
        className="marketplace-card rounded-[12px] p-5"
      >
        <h2
          id="sh-overview-flow"
          className="mb-4 flex items-center gap-2 text-sm font-bold tracking-tight text-[var(--text-primary)]"
        >
          <span className="icon-chip-primary flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm">
            <ShareNetwork aria-hidden weight="duotone" className="size-4" />
          </span>
          {t("flowTitle")}
        </h2>
        <p className="mb-4 text-xs text-[var(--text-muted)]">{t("flowSubtitle")}</p>
        <SystemHealthFlow
          jobs={jobsQuery.data}
          queues={queuesQuery.data}
          outbox={outbox}
          isLoading={isLoading}
        />
      </section>

      {/* Service topology */}
      <section
        aria-labelledby="sh-overview-topology"
        className="marketplace-card rounded-[12px] p-5"
      >
        <h2
          id="sh-overview-topology"
          className="mb-4 flex items-center gap-2 text-sm font-bold tracking-tight text-[var(--text-primary)]"
        >
          <span className="icon-chip-primary flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm">
            <Database aria-hidden weight="duotone" className="size-4" />
          </span>
          {t("topologyTitle")}
        </h2>
        <p className="mb-4 text-xs text-[var(--text-muted)]">{t("topologySubtitle")}</p>
        <SystemHealthTopology
          services={servicesQuery.data}
          queues={queuesQuery.data}
          isLoading={isLoading}
        />
      </section>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Main screen                                                                 */
/* -------------------------------------------------------------------------- */

const TAB_ID_BASE = "system-health";

export function SystemHealthScreen() {
  const t = useTranslations("adminConsole.systemHealth");

  const [activeTab, setActiveTab] = useState("overview");

  const tabItems = [
    { value: "overview", label: t("tabs.overview") },
    { value: "queues-jobs", label: t("tabs.queuesJobs") },
    { value: "services", label: t("tabs.services") },
  ];

  return (
    <>
      <PageHeader
        title={t("pageTitle")}
        actions={
          <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--teal-500)]/40 bg-[var(--teal-50)] px-2.5 py-1 text-[0.6875rem] font-semibold text-[var(--teal-600)]">
            <ArrowClockwise aria-hidden weight="bold" className="size-3 shrink-0" />
            {/* Auto-refresh every 10s */}
            10s
          </span>
        }
      />

      <Tabs
        items={tabItems}
        value={activeTab}
        onValueChange={setActiveTab}
        ariaLabel={t("pageTitle")}
        idBase={TAB_ID_BASE}
      />

      <TabPanel
        tabsId={TAB_ID_BASE}
        value="overview"
        active={activeTab === "overview"}
      >
        <OverviewTab />
      </TabPanel>

      <TabPanel
        tabsId={TAB_ID_BASE}
        value="queues-jobs"
        active={activeTab === "queues-jobs"}
      >
        <QueuesJobsTab />
      </TabPanel>

      <TabPanel
        tabsId={TAB_ID_BASE}
        value="services"
        active={activeTab === "services"}
      >
        <ServicesTab />
      </TabPanel>
    </>
  );
}
