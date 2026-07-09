"use client";

import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle,
  Gavel,
  GraduationCap,
  Handshake,
  ShieldCheck,
  Stack,
  Warning,
  type Icon,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { EmptyState } from "@/components/ui";
import { cn } from "@/lib/utils";
import { dashboardsApi, type UniversityOpsGroup, type UniversityOpsQueue } from "@/lib/api";

/** Icon per function group (falls back to a generic stack). */
const GROUP_ICON: Record<string, Icon> = {
  moderation: Gavel,
  partner_support: Handshake,
  trust_safety: ShieldCheck,
  career_services: GraduationCap,
};

/**
 * University operations command center — the "what needs doing" worklist.
 *
 * Aggregates every operational queue (moderation, partner support, trust &
 * safety, career services) into function groups with open + overdue counts and
 * deep links, from the backend read-model. Labels resolve through local i18n
 * keyed on the stable `group.key` / `queue.kind`, falling back to the
 * server-provided label. Superadmin sees the whole system; ordinary staff see
 * whatever the RBAC-gated endpoint returns.
 */
export function UniversityOpsWorklist() {
  const tu = useTranslations("dashboard.university.ops");

  const query = useQuery({
    queryKey: ["dashboard", "university", "ops"],
    queryFn: () => dashboardsApi.universityOps(),
    retry: false,
  });

  // Non-blocking: if the ops read-model fails, the rest of the dashboard still
  // renders — surface nothing rather than an error wall for a secondary panel.
  if (query.isError) return null;

  return (
    <section aria-labelledby="university-ops-title" className="space-y-3">
      <div className="flex items-center gap-2.5">
        <span className="icon-chip-primary flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm">
          <Stack aria-hidden weight="duotone" className="size-4" />
        </span>
        <div className="min-w-0">
          <h2
            id="university-ops-title"
            className="text-base font-bold tracking-tight text-[var(--text-primary)]"
          >
            {tu("title")}
          </h2>
          <p className="text-xs text-[var(--text-secondary)]">{tu("subtitle")}</p>
        </div>
      </div>

      {query.isPending ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2" aria-busy="true">
          {[0, 1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-40 animate-pulse rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-subtle)]"
            />
          ))}
        </div>
      ) : query.data.totals.open === 0 ? (
        <EmptyState
          kind="empty"
          icon={CheckCircle}
          title={tu("allClearTitle")}
          description={tu("allClearBody")}
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {query.data.groups
            .filter((g) => g.queues.length > 0)
            .map((g) => (
              <OpsGroupCard key={g.key} group={g} />
            ))}
        </div>
      )}
    </section>
  );
}

function OpsGroupCard({ group }: { group: UniversityOpsGroup }) {
  const tu = useTranslations("dashboard.university.ops");
  const GroupIcon = GROUP_ICON[group.key] ?? Stack;
  const groupLabel = tu.has(`group.${group.key}`) ? tu(`group.${group.key}`) : group.label;

  return (
    <div className="marketplace-card flex flex-col rounded-[12px] p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="flex min-w-0 items-center gap-2 text-sm font-bold tracking-tight text-[var(--text-primary)]">
          <span className="icon-chip-neutral flex size-6 shrink-0 items-center justify-center rounded-lg">
            <GroupIcon aria-hidden weight="duotone" className="size-3.5" />
          </span>
          <span className="truncate">{groupLabel}</span>
        </h3>
        {group.overdue_total > 0 && (
          <span className="flex shrink-0 items-center gap-1 rounded-full border border-[var(--red-100)] bg-[var(--red-50)] px-2 py-0.5 text-[10px] font-bold leading-none text-[var(--red-600)]">
            <Warning aria-hidden weight="fill" className="size-3" />
            {group.overdue_total} {tu("overdueLabel")}
          </span>
        )}
      </div>

      <ul className="flex flex-1 flex-col gap-1" role="list">
        {group.queues.map((q) => (
          <OpsQueueRow key={q.key} queue={q} />
        ))}
      </ul>
    </div>
  );
}

function OpsQueueRow({ queue }: { queue: UniversityOpsQueue }) {
  const tu = useTranslations("dashboard.university.ops");
  const label = tu.has(`queue.${queue.kind}`) ? tu(`queue.${queue.kind}`) : queue.label;

  return (
    <li>
      <Link
        href={queue.href}
        className={cn(
          "flex items-center justify-between gap-3 rounded-lg px-2.5 py-2 transition-colors",
          "hover:bg-[var(--bg-muted)] focus-visible:outline-none focus-visible:ring-2",
          "focus-visible:ring-[var(--brand-primary)]/30",
        )}
      >
        <span className="min-w-0 truncate text-sm font-medium text-[var(--text-primary)]">
          {label}
        </span>
        <span className="flex shrink-0 items-center gap-1.5">
          {queue.overdue > 0 && (
            <span
              className="rounded-md bg-[var(--red-50)] px-1.5 py-0.5 font-mono text-[11px] font-bold tabular-nums text-[var(--red-600)]"
              title={tu("overdueLabel")}
            >
              {queue.overdue}
            </span>
          )}
          <span
            className={cn(
              "rounded-md px-1.5 py-0.5 font-mono text-[11px] font-bold tabular-nums",
              queue.open > 0
                ? "bg-[var(--bg-muted)] text-[var(--text-primary)]"
                : "text-[var(--text-muted)]",
            )}
            title={tu("openLabel")}
          >
            {queue.open}
          </span>
        </span>
      </Link>
    </li>
  );
}
