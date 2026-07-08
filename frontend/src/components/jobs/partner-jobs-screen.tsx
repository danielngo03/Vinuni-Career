"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Briefcase,
  ChartLineUp,
  CopySimple,
  Kanban,
  LightbulbFilament,
  Plus,
  ShieldWarning,
  SignIn,
  WarningCircle,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import {
  Button,
  DataTable,
  EmptyState,
  StatusBadge,
  type Column,
} from "@/components/ui";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/layout/page-header";
import { useJobLabels, JOB_STATUS_TONE, MODERATION_TONE } from "@/lib/jobs/labels";
import { formatLocation } from "@/lib/jobs/format";
import { formatDateTime } from "@/lib/format";
import { ApiError, jobsApi, type OwnerJobSummary } from "@/lib/api";
import { useToast } from "@/components/ui";

const STATUS_FILTERS = [
  "all",
  "draft",
  "pending_review",
  "active",
  "rejected",
  "closed",
] as const;

type PartnerJobInsightKey =
  | "insightActiveJobs"
  | "insightPendingJobs"
  | "insightRejectedJobs"
  | "insightAllDrafts";

function derivePartnerJobInsights(rows: OwnerJobSummary[]): PartnerJobInsightKey[] {
  const out: PartnerJobInsightKey[] = [];
  if (rows.length === 0) return out;
  const active = rows.filter((r) => r.status === "active").length;
  const pending = rows.filter((r) => r.status === "pending_review").length;
  const rejected = rows.filter((r) => r.status === "rejected").length;
  const drafts = rows.filter((r) => r.status === "draft").length;
  if (pending > 0) out.push("insightPendingJobs");
  if (rejected > 0) out.push("insightRejectedJobs");
  if (active > 0 && !out.length) out.push("insightActiveJobs");
  if (drafts > 0 && active === 0 && pending === 0) out.push("insightAllDrafts");
  return out.slice(0, 2);
}

export function PartnerJobsScreen() {
  const t = useTranslations("jobs");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useJobLabels();
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();

  const [statusFilter, setStatusFilter] = useState<string>("all");

  const duplicateMutation = useMutation({
    mutationFn: (jobId: string) => jobsApi.duplicate(jobId),
    onSuccess: (copy) => {
      void qc.invalidateQueries({ queryKey: ["jobs", "mine"] });
      toast.show({ tone: "success", title: t("duplicateSuccess") });
      router.push(`/partner/jobs/${copy.id}`);
    },
    onError: () => {
      toast.show({ tone: "error", title: t("duplicateError") });
    },
  });

  const query = useInfiniteQuery({
    queryKey: ["jobs", "mine", statusFilter],
    queryFn: ({ pageParam }) =>
      jobsApi.listMine({
        cursor: pageParam,
        limit: 20,
        status: statusFilter === "all" ? undefined : statusFilter,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.page.next_cursor,
    retry: false,
  });

  const rows: OwnerJobSummary[] = useMemo(
    () => query.data?.pages.flatMap((p) => p.data) ?? [],
    [query.data],
  );

  const newButton = (
    <Link href="/partner/jobs/new">
      <Button variant="primary">
        <Plus aria-hidden weight="bold" className="size-4" />
        {t("newJob")}
      </Button>
    </Link>
  );

  // Permission / auth states.
  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          <PageHeader title={t("manageTitle")} description={t("manageSubtitle")} />
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            icon={err.isPermissionError ? ShieldWarning : SignIn}
            title={
              err.isPermissionError
                ? tStates("permissionTitle")
                : tStates("authTitle")
            }
            description={
              err.isPermissionError ? t("permissionBody") : tStates("authBody")
            }
          />
        </>
      );
    }
  }

  const columns: Column<OwnerJobSummary>[] = [
    {
      key: "title",
      header: t("colTitle"),
      cell: (r) => (
        <Link
          href={`/partner/jobs/${r.id}`}
          className="font-semibold text-[var(--text-primary)] outline-none hover:text-[var(--brand-primary)] focus-visible:underline"
        >
          {r.title}
        </Link>
      ),
    },
    {
      key: "type",
      header: t("colType"),
      cell: (r) => (
        <span className="text-[var(--text-secondary)]">
          {labels.employmentType(r.employment_type, r.employment_type_label)}
          {" · "}
          {labels.locationType(r.location_type, r.location_type_label)}
        </span>
      ),
    },
    {
      key: "location",
      header: t("location"),
      cell: (r) => (
        <span className="text-[var(--text-secondary)]">
          {formatLocation(r.location_city, r.location_country)}
        </span>
      ),
    },
    {
      key: "status",
      header: t("colStatus"),
      cell: (r) => (
        <div className="flex flex-col items-start gap-1">
          <StatusBadge tone={JOB_STATUS_TONE[r.status] ?? "info"}>
            {labels.status(r.status, r.status_label)}
          </StatusBadge>
          {r.status === "pending_review" && (
            <StatusBadge tone={MODERATION_TONE[r.moderation_status] ?? "info"}>
              {labels.moderation(r.moderation_status, r.moderation_status_label)}
            </StatusBadge>
          )}
        </div>
      ),
    },
    {
      key: "created_at",
      header: t("colCreated"),
      cell: (r) => (
        <span className="text-[var(--text-secondary)]">
          {formatDateTime(r.created_at, locale)}
        </span>
      ),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      cell: (r) => (
        <div className="flex items-center justify-end gap-2">
          {r.status === "active" && (
            <Link href={`/partner/jobs/${r.id}/pipeline`}>
              <Button variant="ghost" size="sm">
                <Kanban aria-hidden weight="duotone" className="size-4" />
                {t("pipeline")}
              </Button>
            </Link>
          )}
          <Button
            variant="ghost"
            size="sm"
            disabled={duplicateMutation.isPending}
            onClick={() => duplicateMutation.mutate(r.id)}
            aria-label={t("duplicateAria", { title: r.title })}
          >
            <CopySimple aria-hidden weight="duotone" className="size-4" />
            {t("duplicate")}
          </Button>
          <Link href={`/partner/jobs/${r.id}`}>
            <Button variant="ghost" size="sm">
              {t("manage")}
            </Button>
          </Link>
        </div>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title={t("manageTitle")}
        description={t("manageSubtitle")}
        actions={newButton}
      />

      {/* ── Job posting health — deterministic rollup of the status counts below (not model output) ── */}
      {!query.isPending && statusFilter === "all" && (() => {
        const insights = derivePartnerJobInsights(rows);
        if (!insights.length) return null;
        return (
          <section
            aria-label={t("jobPostingHealthTitle")}
            className="mb-4 rounded-2xl border border-[var(--border-default)] bg-[var(--bg-subtle)] p-4 "
          >
            <div className="mb-3 flex items-center gap-2">
              <span className="flex size-6 items-center justify-center rounded-lg icon-chip-neutral">
                <ChartLineUp aria-hidden weight="duotone" className="size-3.5" />
              </span>
              <p className="text-sm font-semibold text-[var(--text-primary)]">{t("jobPostingHealthTitle")}</p>
            </div>
            <ul className="space-y-1.5">
              {insights.map((key) => (
                <li key={key} className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                  <LightbulbFilament aria-hidden className="mt-0.5 size-3.5 shrink-0 text-[var(--text-muted)]" />
                  {t(key)}
                </li>
              ))}
            </ul>
          </section>
        );
      })()}

      {/* Status filter tab chips */}
      {(() => {
        const CHIP_ACTIVE: Record<string, string> = {
          all: "border-[var(--brand-primary)]/30 bg-[var(--brand-primary)] text-white shadow-sm",
          draft: "border-[var(--gray-500)]/30 bg-[var(--gray-600)] text-white shadow-sm",
          pending_review: "border-[var(--amber-500)]/30 bg-[var(--amber-600)] text-white shadow-sm",
          active: "border-[var(--teal-500)]/30 bg-[var(--teal-600)] text-white shadow-sm",
          rejected: "border-[var(--red-500)]/30 bg-[var(--red-600)] text-white shadow-sm",
          closed: "border-[var(--gray-500)]/30 bg-[var(--gray-600)] text-white shadow-sm",
        };
        return (
          <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label={t("filterStatusLabel")}>
            {STATUS_FILTERS.map((s) => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                aria-pressed={statusFilter === s}
                className={cn(
                  "inline-flex items-center rounded-full border px-3.5 py-1.5 text-xs font-semibold transition-all focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-primary)]",
                  statusFilter === s
                    ? CHIP_ACTIVE[s] ?? CHIP_ACTIVE.all
                    : "border-[var(--border-default)] bg-white text-[var(--text-secondary)] hover:bg-white hover:text-[var(--text-primary)]",
                )}
              >
                {s === "all" ? t("filterAllStatuses") : t(`enums.status.${s}`)}
              </button>
            ))}
          </div>
        );
      })()}

      {query.isError &&
      !(query.error instanceof ApiError && (query.error.isPermissionError || query.error.isAuthError)) ? (
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={tStates("errorTitle")}
          description={tStates("errorBody")}
          action={
            <Button variant="secondary" onClick={() => query.refetch()}>
              {tc("retry")}
            </Button>
          }
        />
      ) : (
        <>
          <DataTable
            columns={columns}
            rows={rows}
            getRowId={(r) => r.id}
            loading={query.isPending}
            caption={t("manageTitle")}
            empty={{
              kind: "empty",
              icon: Briefcase,
              title: statusFilter === "all" ? t("noJobsTitle") : t("noJobsFilterTitle"),
              description: statusFilter === "all" ? t("noJobsBody") : t("noJobsFilterBody"),
              action: statusFilter === "all" ? newButton : undefined,
            }}
          />
          {query.hasNextPage && (
            <div className="mt-6 flex justify-center">
              <Button
                variant="secondary"
                loading={query.isFetchingNextPage}
                onClick={() => query.fetchNextPage()}
              >
                {tc("loadMore")}
              </Button>
            </div>
          )}
        </>
      )}
    </>
  );
}
