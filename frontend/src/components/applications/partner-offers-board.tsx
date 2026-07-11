"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  Briefcase,
  CheckCircle2,
  Handshake,
  ListChecks,
  LogIn,
  Send,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DataTable,
  type ColumnDef,
  DetailSheet,
  EmptyState,
  FilterBar,
  KpiRow,
  KpiTile,
  PageHeader,
  StatusChip,
} from "@/components/kit";
import { formatDateShort, formatDateTimeShort } from "@/lib/format";
import {
  ApiError,
  organizationApi,
  recruitingApi,
  type OfferBoardRow,
  type OfferBoardScope,
  type OfferBoardStatus,
} from "@/lib/api";
import { OFFER_STATUS_CHIP, initials } from "./chip-tones";
import {
  BoardToolbarMenu,
  BoardToolbarRadio,
  SegmentedFilter,
  formatSalary,
} from "./recruiting-board-parts";
import { PartnerOfferPanel } from "./partner-offer-panel";

const nf = new Intl.NumberFormat();

const SCOPES: readonly OfferBoardScope[] = ["all", "live", "needs_action", "terminal"];
const STATUS_OPTIONS: readonly (OfferBoardStatus | "all")[] = [
  "all",
  "draft",
  "pending_approval",
  "approved",
  "sent",
  "accepted",
  "declined",
  "expired",
  "rescinded",
];

/** States where the recruiter is the one who must act next. */
const NEEDS_ACTION: ReadonlySet<string> = new Set(["draft", "pending_approval", "approved"]);

/** Queue weight (lower = higher up) so the recruiter's to-do sits on top. */
const STATUS_WEIGHT: Record<string, number> = {
  pending_approval: 0,
  approved: 1,
  draft: 2,
  sent: 3,
  accepted: 4,
  declined: 5,
  expired: 6,
  rescinded: 7,
};

/**
 * Org-wide Offers board (v10). One bounded `scope=all` snapshot feeds honest KPI
 * counts + a lifecycle scope / status / job client filter; salary is the
 * recruiter's own-org comp (shown per RBAC). Clicking a row opens the full,
 * actionable offer panel (submit/approve/send/rescind) for that application —
 * consequential transitions keep their in-panel confirmation.
 */
export function PartnerOffersBoard() {
  const t = useTranslations("offers");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");

  const [scope, setScope] = React.useState<OfferBoardScope>("all");
  const [statusFilter, setStatusFilter] = React.useState<OfferBoardStatus | "all">("all");
  const [jobFilter, setJobFilter] = React.useState<string>("all");
  const [search, setSearch] = React.useState("");
  const [selected, setSelected] = React.useState<OfferBoardRow | null>(null);

  const query = useQuery({
    queryKey: ["recruiting", "offers", "board"],
    queryFn: () => recruitingApi.listOffersBoard({ scope: "all", limit: 200 }),
    staleTime: 30_000,
    refetchInterval: 60_000,
    retry: false,
  });

  // Caller capabilities gate the create CTA (advisory; service layer is final).
  const capsQuery = useQuery({
    queryKey: ["org", "me", "capabilities"],
    queryFn: () => organizationApi.getMyCapabilities(),
    staleTime: 60_000,
    retry: false,
  });
  const caps = capsQuery.data;
  const canCreate = caps
    ? caps.is_org_admin || caps.grants.includes("offers:create")
    : false;

  const rows = React.useMemo(() => query.data?.offers ?? [], [query.data]);
  const total = query.data?.total ?? rows.length;

  const metrics = React.useMemo(() => {
    let pendingApproval = 0;
    let awaitingSend = 0;
    let sent = 0;
    let accepted = 0;
    for (const r of rows) {
      if (r.status === "pending_approval") pendingApproval += 1;
      else if (r.status === "approved") awaitingSend += 1;
      else if (r.status === "sent") sent += 1;
      else if (r.status === "accepted") accepted += 1;
    }
    return { pendingApproval, awaitingSend, sent, accepted };
  }, [rows]);

  // Distinct jobs present in the loaded offers → honest job picker (only jobs
  // that actually have offers appear).
  const jobs = React.useMemo(() => {
    const map = new Map<string, string>();
    for (const r of rows) if (!map.has(r.job_id)) map.set(r.job_id, r.job_title);
    return Array.from(map, ([id, title]) => ({ id, title }));
  }, [rows]);

  const visibleRows = React.useMemo(() => {
    let out = rows;
    if (scope === "live") out = out.filter((r) => r.is_live);
    else if (scope === "terminal") out = out.filter((r) => !r.is_live);
    else if (scope === "needs_action") out = out.filter((r) => NEEDS_ACTION.has(r.status));
    if (statusFilter !== "all") out = out.filter((r) => r.status === statusFilter);
    if (jobFilter !== "all") out = out.filter((r) => r.job_id === jobFilter);
    const q = search.trim().toLowerCase();
    if (q) {
      out = out.filter(
        (r) =>
          r.candidate_handle.toLowerCase().includes(q) ||
          r.position_title.toLowerCase().includes(q) ||
          r.job_title.toLowerCase().includes(q),
      );
    }
    return [...out].sort((a, b) => {
      const wa = STATUS_WEIGHT[a.status] ?? 9;
      const wb = STATUS_WEIGHT[b.status] ?? 9;
      if (wa !== wb) return wa - wb;
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
  }, [rows, scope, statusFilter, jobFilter, search]);

  const header = <PageHeader title={t("board.title")} subtitle={t("board.subtitle")} />;

  /* ---- permission / auth / error gates ---- */
  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          {header}
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            icon={err.isPermissionError ? ShieldAlert : LogIn}
            title={err.isPermissionError ? tStates("permissionTitle") : tStates("authTitle")}
            description={err.isPermissionError ? tStates("permissionBody") : tStates("authBody")}
          />
        </>
      );
    }
    return (
      <>
        {header}
        <EmptyState
          kind={err.code === "NETWORK_ERROR" ? "offline" : "error"}
          icon={AlertCircle}
          title={tStates("errorTitle")}
          description={tStates("errorBody")}
          action={
            <Button variant="secondary" onClick={() => void query.refetch()}>
              {tc("retry")}
            </Button>
          }
        />
      </>
    );
  }

  const statusText = (row: OfferBoardRow) =>
    STATUS_OPTIONS.includes(row.status)
      ? t(`status.${row.status}`)
      : row.status_label;

  const columns: ColumnDef<OfferBoardRow, unknown>[] = [
    {
      id: "candidate",
      enableSorting: false,
      header: t("board.colCandidate"),
      cell: ({ row }) => {
        const r = row.original;
        return (
          <span className="inline-flex min-w-0 items-center gap-2.5">
            <Avatar size="sm">
              <AvatarFallback>{initials(r.candidate_handle)}</AvatarFallback>
            </Avatar>
            <span className="min-w-0 truncate font-medium text-foreground">
              {r.candidate_handle}
            </span>
          </span>
        );
      },
    },
    {
      id: "position",
      enableSorting: false,
      header: t("board.colPosition"),
      cell: ({ row }) => {
        const r = row.original;
        return (
          <span className="min-w-0">
            <span className="block truncate text-foreground">{r.position_title}</span>
            {r.job_title && r.job_title !== r.position_title && (
              <span className="type-caption text-muted-foreground">{r.job_title}</span>
            )}
          </span>
        );
      },
    },
    {
      id: "salary",
      enableSorting: false,
      header: t("board.colSalary"),
      cell: ({ row }) => {
        const r = row.original;
        const salary = formatSalary(r.salary_amount, r.salary_currency, r.period_label);
        return salary ? (
          <span className="type-small tabular-nums text-foreground">{salary}</span>
        ) : (
          <span className="type-small text-muted-foreground">—</span>
        );
      },
    },
    {
      id: "deadline",
      enableSorting: false,
      header: t("board.colDeadline"),
      meta: { align: "right" },
      cell: ({ row }) => (
        <span
          className="type-small tabular-nums text-muted-foreground"
          title={formatDateTimeShort(row.original.expiry_date)}
        >
          {formatDateShort(row.original.expiry_date)}
        </span>
      ),
    },
    {
      id: "status",
      enableSorting: false,
      header: t("board.colStatus"),
      meta: { align: "right" },
      cell: ({ row }) => (
        <span className="flex justify-end">
          <StatusChip tone={OFFER_STATUS_CHIP[row.original.status] ?? "neutral"}>
            {statusText(row.original)}
          </StatusChip>
        </span>
      ),
    },
  ];

  const noData = rows.length === 0;
  const jobFilterValue =
    jobFilter === "all"
      ? t("board.jobAll")
      : jobs.find((j) => j.id === jobFilter)?.title ?? t("board.jobAll");

  return (
    <>
      {header}
      <div className="space-y-4">
        <KpiRow cols={4}>
          <KpiTile
            label={t("board.kpiPendingApproval")}
            value={query.isPending ? "—" : nf.format(metrics.pendingApproval)}
            icon={ShieldCheck}
            hint={metrics.pendingApproval > 0 ? t("board.kpiPendingApprovalHint") : undefined}
          />
          <KpiTile
            label={t("board.kpiAwaitingSend")}
            value={query.isPending ? "—" : nf.format(metrics.awaitingSend)}
            icon={Send}
            hint={metrics.awaitingSend > 0 ? t("board.kpiAwaitingSendHint") : undefined}
          />
          <KpiTile
            label={t("board.kpiSent")}
            value={query.isPending ? "—" : nf.format(metrics.sent)}
            icon={Handshake}
          />
          <KpiTile
            label={t("board.kpiAccepted")}
            value={query.isPending ? "—" : nf.format(metrics.accepted)}
            icon={CheckCircle2}
          />
        </KpiRow>

        <FilterBar
          search={{
            value: search,
            onChange: setSearch,
            placeholder: t("board.searchPlaceholder"),
            ariaLabel: t("board.searchPlaceholder"),
          }}
          actions={
            !query.isPending && rows.length > 0 ? (
              <span className="type-caption tabular-nums text-muted-foreground">
                {rows.length < total
                  ? t("board.boundedHint", { shown: rows.length, total })
                  : t("board.resultCount", { count: visibleRows.length })}
              </span>
            ) : undefined
          }
        >
          <SegmentedFilter
            value={scope}
            options={SCOPES}
            onChange={setScope}
            label={t("board.scopeLabel")}
            optionLabel={(s) => t(`board.scope_${s}`)}
          />
          <BoardToolbarMenu
            icon={ListChecks}
            label={t("board.filterStatusLabel")}
            value={statusFilter === "all" ? t("board.statusAll") : t(`status.${statusFilter}`)}
          >
            <BoardToolbarRadio
              label={t("board.filterStatusLabel")}
              value={statusFilter}
              onChange={setStatusFilter}
              options={STATUS_OPTIONS.map((s) => ({
                value: s,
                label: s === "all" ? t("board.statusAll") : t(`status.${s}`),
              }))}
            />
          </BoardToolbarMenu>
          {jobs.length > 1 && (
            <BoardToolbarMenu
              icon={Briefcase}
              label={t("board.jobFilterLabel")}
              value={jobFilterValue}
            >
              <BoardToolbarRadio
                label={t("board.jobFilterLabel")}
                value={jobFilter}
                onChange={setJobFilter}
                options={[
                  { value: "all", label: t("board.jobAll") },
                  ...jobs.map((j) => ({ value: j.id, label: j.title })),
                ]}
              />
            </BoardToolbarMenu>
          )}
        </FilterBar>

        <DataTable
          columns={columns}
          data={visibleRows}
          getRowId={(r) => r.id}
          loading={query.isPending}
          pageSize={12}
          activeRowId={selected?.id}
          onRowClick={(r) => setSelected(r)}
          empty={
            <EmptyState
              kind="empty"
              icon={Handshake}
              title={noData ? t("board.emptyTitle") : t("board.noMatchTitle")}
              description={noData ? t("board.emptyBody") : t("board.noMatchBody")}
              action={
                !noData ? (
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setScope("all");
                      setStatusFilter("all");
                      setJobFilter("all");
                      setSearch("");
                    }}
                  >
                    {t("board.clearFilters")}
                  </Button>
                ) : undefined
              }
            />
          }
        />
      </div>

      {/* Offer detail drawer — full actionable panel for the application.
          Refetch the board on close so a submit/approve/send/rescind taken inside
          the panel is reflected in the list + KPIs immediately. */}
      <DetailSheet
        open={!!selected}
        onClose={() => {
          setSelected(null);
          void query.refetch();
        }}
        width="lg"
        closeLabel={tc("close")}
        title={selected?.candidate_handle ?? ""}
        subtitle={selected?.position_title}
        avatar={
          selected ? (
            <Avatar size="lg">
              <AvatarFallback>{initials(selected.candidate_handle)}</AvatarFallback>
            </Avatar>
          ) : undefined
        }
        status={
          selected ? (
            <>
              <StatusChip tone={OFFER_STATUS_CHIP[selected.status] ?? "neutral"}>
                {statusText(selected)}
              </StatusChip>
              {selected.job_title && selected.job_title !== selected.position_title && (
                <StatusChip tone="indigo" size="sm">
                  {selected.job_title}
                </StatusChip>
              )}
            </>
          ) : undefined
        }
      >
        {selected && (
          <div className="p-5">
            <PartnerOfferPanel
              key={selected.application_id}
              applicationId={selected.application_id}
              canCreate={canCreate}
            />
          </div>
        )}
      </DetailSheet>
    </>
  );
}
