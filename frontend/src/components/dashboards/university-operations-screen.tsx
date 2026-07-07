"use client";

import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  Briefcase,
  CalendarBlank,
  CheckCircle,
  ClipboardText,
  Clock,
  Gavel,
  Handshake,
  Megaphone,
  ShieldWarning,
  UsersThree,
  Warning,
} from "@phosphor-icons/react";
import type { Icon } from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/ui";
import { formatDateTime } from "@/lib/format";
import {
  dashboardsApi,
  type OperationsHealth,
  type OperationsQueue,
  type OperationsTask,
  type UniversityOperations,
} from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import { cn } from "@/lib/utils";
import {
  DashboardErrorState,
  DashboardGuestGate,
  DashboardSkeleton,
  MetricTiles,
  type MetricItem,
} from "./dashboard-kit";

/* -------------------------------------------------------------------------- */
/* Health traffic-light tokens (teal / amber / red — DESIGN.md semantic use)  */
/* -------------------------------------------------------------------------- */

const HEALTH_TOKENS: Record<
  OperationsHealth,
  { dot: string; badge: string; icon: Icon }
> = {
  on_track: {
    dot: "bg-[var(--teal-600)]",
    badge: "border-[var(--teal-100)] bg-[var(--teal-50)] text-[var(--teal-700)]",
    icon: CheckCircle,
  },
  due_soon: {
    dot: "bg-[var(--amber-600)]",
    badge: "border-[var(--amber-100)] bg-[var(--amber-50)] text-[var(--amber-700)]",
    icon: Clock,
  },
  breached: {
    dot: "bg-[var(--brand-red)]",
    badge: "border-[var(--red-100)] bg-[var(--red-50)] text-[var(--red-600)]",
    icon: Warning,
  },
};

const QUEUE_ICONS: Record<OperationsQueue["key"], Icon> = {
  jobs: Briefcase,
  events: CalendarBlank,
  ads: Megaphone,
  partner_registrations: Handshake,
  ai_review: ShieldWarning,
};

/* -------------------------------------------------------------------------- */

export function UniversityOperationsScreen() {
  const t = useTranslations("universityOperations");
  const tNav = useTranslations("nav");
  const locale = useLocale();
  const status = useAuthStore((s) => s.status);
  const authed = status === "authenticated";

  const query = useQuery({
    queryKey: ["dashboard", "university", "operations"],
    queryFn: () => dashboardsApi.universityOperations(),
    enabled: authed,
    retry: false,
  });

  return (
    <>
      <PageHeader title={tNav("operations")} description={t("subtitle")} />

      {!authed ? (
        <DashboardGuestGate persona="university" />
      ) : query.isPending ? (
        <DashboardSkeleton tileCount={4} tileCols={4} />
      ) : query.isError ? (
        <DashboardErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : (
        <OperationsBody data={query.data} locale={locale} />
      )}
    </>
  );
}

function OperationsBody({
  data,
  locale,
}: {
  data: UniversityOperations;
  locale: string;
}) {
  const t = useTranslations("universityOperations");

  const slaTiles: MetricItem[] = [
    {
      key: "pending",
      label: t("sla.pending"),
      value: data.sla.total_pending,
      icon: ClipboardText,
    },
    {
      key: "overdue",
      label: t("sla.overdue"),
      value: data.sla.total_overdue,
      icon: Warning,
      emphasize: true,
      hotNote:
        data.sla.total_overdue > 0
          ? t("sla.overdueHotNote", { count: data.sla.total_overdue })
          : undefined,
    },
    {
      key: "due_soon",
      label: t("sla.dueSoon"),
      value: data.sla.total_due_soon,
      icon: Clock,
      tone: "warning",
    },
    {
      key: "breach_rate",
      label: t("sla.breachRate"),
      value: Math.round(data.sla.breach_rate * 100),
      icon: Gavel,
      percent: true,
      tone: data.sla.total_overdue > 0 ? "danger" : "success",
    },
  ];

  return (
    <div className="space-y-6">
      {/* SLA-breach banner — only when something is actually overdue. */}
      {data.sla.total_overdue > 0 && (
        <div
          role="alert"
          className="flex items-start gap-3 rounded-[12px] border border-[var(--red-100)] bg-[var(--red-50)] px-4 py-3"
        >
          <Warning
            aria-hidden
            weight="fill"
            className="mt-0.5 size-5 shrink-0 text-[var(--brand-red)]"
          />
          <p className="text-sm font-medium text-[var(--text-primary)]">
            {t("breach.banner", { count: data.sla.total_overdue })}
          </p>
        </div>
      )}

      {/* SLA roll-up tiles */}
      <MetricTiles items={slaTiles} />

      {/* Queue health cards */}
      <section aria-label={t("queues.title")}>
        <h2 className="mb-3 text-sm font-bold tracking-tight text-[var(--text-primary)]">
          {t("queues.title")}
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {data.queues.map((q) => (
            <QueueCard key={q.key} queue={q} />
          ))}
        </div>
      </section>

      {/* Two-column: tasks + risk (left) / workload + events (right) */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <ActionableTasks tasks={data.actionable_tasks} />
          <RiskMix risk={data.risk} />
        </div>
        <div className="space-y-4">
          <Workload workload={data.workload} />
          <UpcomingEvents events={data.upcoming_events} locale={locale} />
        </div>
      </div>
    </div>
  );
}

function QueueCard({ queue }: { queue: OperationsQueue }) {
  const t = useTranslations("universityOperations");
  const health = HEALTH_TOKENS[queue.health];
  const QueueIcon = QUEUE_ICONS[queue.key];
  const HealthIcon = health.icon;

  return (
    <Link
      href={queue.href}
      className="marketplace-card group flex flex-col gap-3 rounded-[12px] p-4 outline-none transition-shadow duration-200 hover:shadow-md focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
          <span className="icon-chip-primary flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm">
            <QueueIcon aria-hidden weight="duotone" className="size-4" />
          </span>
          {t(`queue.${queue.key}`)}
        </span>
        <span
          className={cn(
            "flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-bold leading-none",
            health.badge,
          )}
        >
          <HealthIcon aria-hidden weight="fill" className="size-3" />
          {t(`health.${queue.health}`)}
        </span>
      </div>

      <div className="flex items-end justify-between">
        <div>
          <p className="text-2xl font-bold tracking-tight text-[var(--text-primary)]">
            {queue.pending}
          </p>
          <p className="text-xs text-[var(--text-secondary)]">{t("card.pending")}</p>
        </div>
        <div className="flex flex-col items-end gap-0.5 text-xs">
          {queue.overdue > 0 && (
            <span className="font-semibold text-[var(--brand-red)]">
              {t("card.overdue", { count: queue.overdue })}
            </span>
          )}
          {queue.due_soon > 0 && (
            <span className="font-semibold text-[var(--amber-700)]">
              {t("card.dueSoon", { count: queue.due_soon })}
            </span>
          )}
          {queue.sla_hours != null && (
            <span className="text-[var(--text-muted)]">
              {t("card.slaWindow", { hours: queue.sla_hours })}
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}

function ActionableTasks({ tasks }: { tasks: OperationsTask[] }) {
  const t = useTranslations("universityOperations");

  return (
    <div className="marketplace-card rounded-[12px] p-4">
      <h3 className="mb-3 text-sm font-bold tracking-tight text-[var(--text-primary)]">
        {t("tasks.title")}
      </h3>
      {tasks.length === 0 ? (
        <EmptyState
          icon={CheckCircle}
          title={t("tasks.emptyTitle")}
          description={t("tasks.emptyBody")}
        />
      ) : (
        <ul className="space-y-2">
          {tasks.map((task) => (
            <TaskRow key={task.queue} task={task} />
          ))}
        </ul>
      )}
    </div>
  );
}

const PRIORITY_BADGE: Record<OperationsTask["priority"], string> = {
  breach: "border-[var(--red-100)] bg-[var(--red-50)] text-[var(--red-600)]",
  due_soon: "border-[var(--amber-100)] bg-[var(--amber-50)] text-[var(--amber-700)]",
  normal: "border-[var(--border-subtle)] bg-[var(--bg-subtle)] text-[var(--text-secondary)]",
};

function TaskRow({ task }: { task: OperationsTask }) {
  const t = useTranslations("universityOperations");
  return (
    <li>
      <Link
        href={task.href}
        className="flex items-center justify-between gap-3 rounded-[10px] border border-[var(--border-subtle)] px-3 py-2.5 outline-none transition-colors duration-200 hover:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
      >
        <span className="flex min-w-0 items-center gap-2">
          <span
            className={cn(
              "shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase leading-none",
              PRIORITY_BADGE[task.priority],
            )}
          >
            {t(`priority.${task.priority}`)}
          </span>
          <span className="truncate text-sm font-medium text-[var(--text-primary)]">
            {t(`queue.${task.queue}`)}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-2 text-xs text-[var(--text-secondary)]">
          {task.overdue > 0 && (
            <span className="font-semibold text-[var(--brand-red)]">
              {t("card.overdue", { count: task.overdue })}
            </span>
          )}
          <span>{t("tasks.pending", { count: task.pending })}</span>
        </span>
      </Link>
    </li>
  );
}

function RiskMix({ risk }: { risk: UniversityOperations["risk"] }) {
  const t = useTranslations("universityOperations");
  const cells: { key: string; label: string; value: number; tone: string }[] = [
    { key: "high", label: t("risk.high"), value: risk.high, tone: "text-[var(--brand-red)]" },
    { key: "medium", label: t("risk.medium"), value: risk.medium, tone: "text-[var(--amber-700)]" },
    { key: "low", label: t("risk.low"), value: risk.low, tone: "text-[var(--text-secondary)]" },
    {
      key: "flagged",
      label: t("risk.flagged"),
      value: risk.flagged_listings,
      tone: "text-[var(--text-primary)]",
    },
  ];
  return (
    <div className="marketplace-card rounded-[12px] p-4">
      <h3 className="mb-1 text-sm font-bold tracking-tight text-[var(--text-primary)]">
        {t("risk.title")}
      </h3>
      <p className="mb-3 text-xs text-[var(--text-muted)]">{t("risk.hint")}</p>
      <div className="grid grid-cols-4 gap-2">
        {cells.map((c) => (
          <div
            key={c.key}
            className="rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-2 py-3 text-center"
          >
            <p className={cn("text-xl font-bold tabular-nums", c.tone)}>{c.value}</p>
            <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">{c.label}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function Workload({ workload }: { workload: UniversityOperations["workload"] }) {
  const t = useTranslations("universityOperations");
  const hasAny =
    workload.by_department.length > 0 ||
    workload.by_moderator.length > 0 ||
    workload.unassigned > 0;
  const maxDept = Math.max(1, ...workload.by_department.map((d) => d.count));

  return (
    <div className="marketplace-card rounded-[12px] p-4">
      <h3 className="mb-3 flex items-center gap-2 text-sm font-bold tracking-tight text-[var(--text-primary)]">
        <span className="icon-chip-primary flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm">
          <UsersThree aria-hidden weight="duotone" className="size-4" />
        </span>
        {t("workload.title")}
      </h3>

      {!hasAny ? (
        <p className="text-sm text-[var(--text-secondary)]">{t("workload.empty")}</p>
      ) : (
        <div className="space-y-3">
          {workload.unassigned > 0 && (
            <div className="flex items-center justify-between rounded-[10px] border border-[var(--amber-100)] bg-[var(--amber-50)] px-3 py-2">
              <span className="text-xs font-semibold text-[var(--amber-700)]">
                {t("workload.unassigned")}
              </span>
              <span className="text-sm font-bold tabular-nums text-[var(--amber-700)]">
                {workload.unassigned}
              </span>
            </div>
          )}

          {workload.by_department.length > 0 && (
            <div className="space-y-2">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                {t("workload.byDepartment")}
              </p>
              {workload.by_department.map((d) => (
                <div key={d.department} className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="truncate text-[var(--text-secondary)]">
                      {d.department === "unassigned" ? t("workload.noDepartment") : d.department}
                    </span>
                    <span className="font-semibold tabular-nums text-[var(--text-primary)]">
                      {d.count}
                    </span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-[var(--bg-subtle)]">
                    <div
                      className="h-full rounded-full bg-[var(--text-primary)]"
                      style={{ width: `${Math.round((d.count / maxDept) * 100)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function UpcomingEvents({
  events,
  locale,
}: {
  events: UniversityOperations["upcoming_events"];
  locale: string;
}) {
  const t = useTranslations("universityOperations");
  return (
    <div className="marketplace-card rounded-[12px] p-4">
      <h3 className="mb-3 flex items-center gap-2 text-sm font-bold tracking-tight text-[var(--text-primary)]">
        <span className="icon-chip-primary flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm">
          <CalendarBlank aria-hidden weight="duotone" className="size-4" />
        </span>
        {t("events.title")}
      </h3>
      {events.length === 0 ? (
        <p className="text-sm text-[var(--text-secondary)]">{t("events.empty")}</p>
      ) : (
        <ul className="space-y-2.5">
          {events.map((ev) => (
            <li key={ev.id} className="border-b border-[var(--border-subtle)] pb-2.5 last:border-0 last:pb-0">
              <p className="truncate text-sm font-medium text-[var(--text-primary)]">{ev.title}</p>
              <div className="mt-0.5 flex items-center justify-between text-xs text-[var(--text-secondary)]">
                <span>{ev.starts_at ? formatDateTime(ev.starts_at, locale) : "—"}</span>
                <span>
                  {ev.seats_left == null
                    ? t("events.registered", { count: ev.registration_count })
                    : t("events.seatsLeft", { count: ev.seats_left })}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
