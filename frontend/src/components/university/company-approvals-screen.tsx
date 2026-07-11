"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Check, FileText, Hourglass, Paperclip, X } from "lucide-react";
import { Button, Modal, Textarea, useToast, SegmentedControl } from "@/components/ui";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  DataTable,
  type ColumnDef,
  DetailSheet,
  DetailSheetSection,
  DetailRow,
  EmptyState,
  FilterBar,
  KpiTile,
  PageHeader,
  StatusChip,
  type ChipTone,
} from "@/components/kit";
import {
  CompanyChangeDiff,
  CompanyDocumentList,
} from "@/components/organization/company-review-shared";
import {
  ApiError,
  companyProfileApi,
  type CompanyChangeRequest,
  type CompanyChangeStatus,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { formatDateTime } from "@/lib/format";

const STATUS_CHIP: Record<string, ChipTone> = {
  pending: "warning",
  approved: "success",
  rejected: "danger",
  withdrawn: "neutral",
};

/**
 * University company-approval queue. Partner admins can edit cosmetic company
 * fields freely, but sensitive LEGAL identity changes (legal name, tax code,
 * business registration number) and any attached document accumulate on a
 * pending change request that a university reviewer must approve or reject.
 *
 * Every state degrades honestly: loading skeleton, empty queue, permission
 * (non-university actor), auth, and a generic error with retry. Decisions are
 * version-checked (stale → 409 conflict), and the queue refetches on success.
 */
export function CompanyApprovalsScreen() {
  const t = useTranslations("companyApprovals");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const [statusFilter, setStatusFilter] = React.useState<CompanyChangeStatus>("pending");
  const [search, setSearch] = React.useState("");
  const [selected, setSelected] = React.useState<CompanyChangeRequest | null>(null);
  const [approveOpen, setApproveOpen] = React.useState(false);
  const [rejectOpen, setRejectOpen] = React.useState(false);
  const [note, setNote] = React.useState("");
  const [reason, setReason] = React.useState("");
  const [reasonError, setReasonError] = React.useState<string | null>(null);

  const query = useQuery({
    queryKey: ["company-approvals", statusFilter],
    queryFn: () => companyProfileApi.listApprovals(statusFilter),
    retry: false,
  });

  const pendingQuery = useQuery({
    queryKey: ["company-approvals", "pending", "count"],
    queryFn: () => companyProfileApi.listApprovals("pending"),
    retry: false,
    staleTime: 30_000,
  });

  const refresh = React.useCallback(() => {
    void qc.invalidateQueries({ queryKey: ["company-approvals"] });
  }, [qc]);

  const handleMutationError = React.useCallback(
    (e: unknown) => {
      const reasonCode =
        e instanceof ApiError && typeof e.details?.reason === "string" ? e.details.reason : undefined;
      if (reasonCode === "version_conflict" || (e instanceof ApiError && e.isConflict)) {
        toast.show({ tone: "error", title: t("conflictToast"), description: t("conflictBody") });
        setApproveOpen(false);
        setRejectOpen(false);
        setSelected(null);
        refresh();
        return;
      }
      toast.show({ tone: "error", title: getMessage(e) });
    },
    [getMessage, refresh, t, toast],
  );

  const approve = useMutation({
    mutationFn: (req: CompanyChangeRequest) =>
      companyProfileApi.approve(req.id, { note: note || null, version: req.version }),
    onSuccess: () => {
      setApproveOpen(false);
      setSelected(null);
      setNote("");
      toast.show({ tone: "success", title: t("approvedToast") });
      refresh();
    },
    onError: handleMutationError,
  });

  const reject = useMutation({
    mutationFn: (req: CompanyChangeRequest) =>
      companyProfileApi.reject(req.id, { reason, version: req.version }),
    onSuccess: () => {
      setRejectOpen(false);
      setSelected(null);
      setReason("");
      toast.show({ tone: "success", title: t("rejectedToast") });
      refresh();
    },
    onError: handleMutationError,
  });

  const rows = query.data ?? [];
  const pendingCount = pendingQuery.data?.length ?? 0;
  const isPending = selected?.status === "pending";

  const changeSummary = (req: CompanyChangeRequest): string => {
    const parts: string[] = [];
    if (req.changes.length > 0) parts.push(req.changes.map((c) => c.label).join(", "));
    if (req.documents.length > 0) parts.push(t("docsCount", { count: req.documents.length }));
    return parts.join(" · ") || "—";
  };

  const columns: ColumnDef<CompanyChangeRequest, unknown>[] = [
    {
      accessorKey: "company_name",
      header: t("company"),
      cell: ({ row }) => {
        const r = row.original;
        return (
          <div className="flex min-w-0 items-center gap-2.5">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-[var(--viz-indigo-soft)]">
              <Building2 className="size-4 text-[var(--viz-indigo)]" strokeWidth={1.8} />
            </span>
            <div className="min-w-0">
              <p className="truncate font-semibold text-foreground">{r.company_name ?? "—"}</p>
              <p className="truncate type-caption text-muted-foreground">{changeSummary(r)}</p>
            </div>
          </div>
        );
      },
    },
    {
      accessorKey: "created_at",
      header: t("submitted"),
      cell: ({ row }) => (
        <span className="whitespace-nowrap type-small text-muted-foreground">
          {row.original.created_at ? formatDateTime(row.original.created_at, locale) : "—"}
        </span>
      ),
    },
    {
      accessorKey: "status",
      header: t("status"),
      cell: ({ row }) => (
        <StatusChip tone={STATUS_CHIP[row.original.status] ?? "neutral"} dot>
          {row.original.status_label}
        </StatusChip>
      ),
    },
  ];

  const header = <PageHeader title={t("title")} subtitle={t("subtitle")} />;

  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          {header}
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            title={err.isPermissionError ? tStates("permissionTitle") : tStates("authTitle")}
            description={err.isPermissionError ? t("permissionBody") : tStates("authBody")}
          />
        </>
      );
    }
  }

  const isHardError =
    query.isError &&
    !(query.error instanceof ApiError && (query.error.isPermissionError || query.error.isAuthError));

  return (
    <>
      {header}

      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3 sm:gap-4">
          <KpiTile
            label={t("kpiPending")}
            value={pendingQuery.isPending ? "—" : String(pendingCount)}
            icon={Hourglass}
          />
          <KpiTile
            label={t("kpiInView")}
            value={query.isPending ? "—" : String(rows.length)}
            icon={FileText}
          />
        </div>

        <Card>
          <CardHeader>
            <div>
              <CardTitle>{t("title")}</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <FilterBar search={{ value: search, onChange: setSearch, placeholder: t("searchPlaceholder") }}>
              <SegmentedControl
                ariaLabel={t("filterLabel")}
                value={statusFilter}
                onValueChange={(v) => setStatusFilter(v as CompanyChangeStatus)}
                size="sm"
                options={[
                  { value: "pending", label: t("filterPending") },
                  { value: "approved", label: t("filterApproved") },
                  { value: "rejected", label: t("filterRejected") },
                ]}
              />
            </FilterBar>

            {isHardError ? (
              <EmptyState
                kind="error"
                title={tStates("errorTitle")}
                description={tStates("errorBody")}
                action={
                  <Button variant="secondary" onClick={() => query.refetch()}>
                    {tc("retry")}
                  </Button>
                }
              />
            ) : (
              <DataTable
                columns={columns}
                data={rows}
                getRowId={(r) => r.id}
                loading={query.isPending}
                globalFilter={search}
                onRowClick={(r) => setSelected(r)}
                activeRowId={selected?.id}
                empty={<EmptyState kind="empty" title={t("empty")} description={t("emptyBody")} />}
              />
            )}
          </CardContent>
        </Card>
      </div>

      {/* Detail drawer */}
      <DetailSheet
        open={selected !== null && !approveOpen && !rejectOpen}
        onClose={() => setSelected(null)}
        title={selected?.company_name ?? t("detailTitle")}
        subtitle={
          selected?.created_at
            ? t("submittedAt", { date: formatDateTime(selected.created_at, locale) })
            : undefined
        }
        closeLabel={tc("close")}
        avatar={
          <span className="flex size-10 items-center justify-center rounded-xl bg-[var(--viz-indigo-soft)]">
            <Building2 className="size-5 text-[var(--viz-indigo)]" strokeWidth={1.8} />
          </span>
        }
        status={
          selected ? (
            <StatusChip tone={STATUS_CHIP[selected.status] ?? "neutral"} dot>
              {selected.status_label}
            </StatusChip>
          ) : undefined
        }
        footer={
          selected && isPending ? (
            <>
              <Button
                variant="ghost"
                size="sm"
                className="text-[var(--content-danger)]"
                onClick={() => {
                  setReason("");
                  setReasonError(null);
                  setRejectOpen(true);
                }}
              >
                <X className="size-4" strokeWidth={1.8} />
                {t("reject")}
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  setNote("");
                  setApproveOpen(true);
                }}
              >
                <Check className="size-4" strokeWidth={2} />
                {t("approve")}
              </Button>
            </>
          ) : undefined
        }
      >
        {selected && (
          <>
            <DetailSheetSection title={t("proposedChanges")}>
              <CompanyChangeDiff
                changes={selected.changes}
                emptyValueLabel={t("valueEmpty")}
                emptyLabel={t("noFieldChanges")}
              />
            </DetailSheetSection>

            <DetailSheetSection title={t("attachedDocs")}>
              <CompanyDocumentList
                documents={selected.documents}
                emptyLabel={t("docsEmpty")}
                viewLabel={t("view")}
              />
            </DetailSheetSection>

            {!isPending && (
              <DetailSheetSection>
                <dl className="space-y-0.5">
                  {selected.decided_at && (
                    <DetailRow label={t("decidedAtLabel")}>
                      {formatDateTime(selected.decided_at, locale)}
                    </DetailRow>
                  )}
                </dl>
                {selected.review_note && (
                  <div className="mt-3 rounded-lg bg-[var(--bg-subtle)] px-3 py-2.5">
                    <p className="type-caption font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                      {t("reviewNote")}
                    </p>
                    <p className="mt-1 text-[0.8125rem] text-foreground">{selected.review_note}</p>
                  </div>
                )}
                <p className="mt-3 type-small text-muted-foreground">{t("alreadyReviewed")}</p>
              </DetailSheetSection>
            )}
          </>
        )}
      </DetailSheet>

      {/* Approve modal */}
      <Modal
        open={approveOpen}
        onClose={() => setApproveOpen(false)}
        title={t("approveTitle")}
        description={t("approveBody", { company: selected?.company_name ?? "" })}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setApproveOpen(false)}>
              {tc("cancel")}
            </Button>
            <Button variant="primary" loading={approve.isPending} onClick={() => selected && approve.mutate(selected)}>
              {t("approveConfirm")}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {selected && (
            <div className="flex items-start gap-2 rounded-lg bg-[var(--bg-subtle)] px-3 py-2 text-[0.8125rem] text-muted-foreground">
              <Paperclip aria-hidden className="mt-0.5 size-4 shrink-0" strokeWidth={1.8} />
              <span>{changeSummary(selected)}</span>
            </div>
          )}
          <Textarea label={t("noteOptional")} rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
      </Modal>

      {/* Reject modal */}
      <Modal
        open={rejectOpen}
        onClose={() => setRejectOpen(false)}
        title={t("rejectTitle")}
        description={t("rejectBody", { company: selected?.company_name ?? "" })}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setRejectOpen(false)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="danger"
              loading={reject.isPending}
              onClick={() => {
                if (!reason.trim()) {
                  setReasonError(t("reasonRequired"));
                  return;
                }
                if (selected) reject.mutate(selected);
              }}
            >
              {t("rejectConfirm")}
            </Button>
          </>
        }
      >
        <Textarea
          label={t("reason")}
          required
          rows={3}
          value={reason}
          error={reasonError ?? undefined}
          onChange={(e) => {
            setReason(e.target.value);
            if (reasonError) setReasonError(null);
          }}
        />
      </Modal>
    </>
  );
}
