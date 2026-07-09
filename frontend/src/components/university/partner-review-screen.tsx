"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  Check,
  CheckCircle2,
  ExternalLink,
  Hourglass,
  ListChecks,
  X,
  XCircle,
} from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Button, Modal, Select, Textarea, useToast, SegmentedControl } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
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
  KpiRow,
  KpiTile,
  StatusChip,
  type ChipTone,
} from "@/components/kit";
import { ApiError, partnerApi, type PartnerRegistration, type TrustLevel } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { formatDateTime } from "@/lib/format";

const STATUS_CHIP: Record<string, ChipTone> = {
  pending_review: "warning",
  approved: "success",
  rejected: "danger",
};

const STATUS_LABEL_KEY: Record<string, string> = {
  pending_review: "filterPending",
  approved: "filterApproved",
  rejected: "filterRejected",
};

export function PartnerReviewScreen() {
  const t = useTranslations("partnersReview");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const [statusFilter, setStatusFilter] = React.useState<string>("pending_review");
  const [search, setSearch] = React.useState("");
  const [selected, setSelected] = React.useState<PartnerRegistration | null>(null);
  const [approveOpen, setApproveOpen] = React.useState(false);
  const [rejectOpen, setRejectOpen] = React.useState(false);
  const [trustLevel, setTrustLevel] = React.useState<TrustLevel>("standard");
  const [note, setNote] = React.useState("");
  const [reason, setReason] = React.useState("");
  const [reasonError, setReasonError] = React.useState<string | null>(null);

  const query = useQuery({
    queryKey: ["admin", "partners", statusFilter],
    queryFn: () => partnerApi.listRegistrations(statusFilter === "all" ? undefined : statusFilter),
    retry: false,
  });

  const allQuery = useQuery({
    queryKey: ["admin", "partners", "all", "counts"],
    queryFn: () => partnerApi.listRegistrations(),
    retry: false,
    staleTime: 30_000,
  });

  const refresh = React.useCallback(() => {
    void qc.invalidateQueries({ queryKey: ["admin", "partners"] });
  }, [qc]);

  const handleMutationError = React.useCallback(
    (e: unknown) => {
      const reasonCode =
        e instanceof ApiError && typeof e.details?.reason === "string" ? e.details.reason : undefined;
      if (reasonCode === "version_conflict" || (e instanceof ApiError && e.code === "CONFLICT")) {
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
    mutationFn: (reg: PartnerRegistration) =>
      partnerApi.approve(reg.id, { trust_level: trustLevel, note: note || null, version: reg.version }),
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
    mutationFn: (reg: PartnerRegistration) => partnerApi.reject(reg.id, { reason, version: reg.version }),
    onSuccess: () => {
      setRejectOpen(false);
      setSelected(null);
      setReason("");
      toast.show({ tone: "success", title: t("rejectedToast") });
      refresh();
    },
    onError: handleMutationError,
  });

  const allItems = allQuery.data ?? [];
  const countPending = allItems.filter((r) => r.status === "pending_review").length;
  const countApproved = allItems.filter((r) => r.status === "approved").length;
  const countRejected = allItems.filter((r) => r.status === "rejected").length;
  const rows = query.data ?? [];
  const isPending = selected?.status === "pending_review";

  const statusText = (reg: PartnerRegistration) =>
    STATUS_LABEL_KEY[reg.status] ? t(STATUS_LABEL_KEY[reg.status]!) : reg.status_label;

  const columns: ColumnDef<PartnerRegistration, unknown>[] = [
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
              <p className="truncate font-semibold text-foreground">{r.company_name}</p>
              <p className="truncate type-caption text-muted-foreground">
                {[r.industry, r.company_size].filter(Boolean).join(" · ") || "—"}
              </p>
            </div>
          </div>
        );
      },
    },
    {
      accessorKey: "contact_name",
      header: t("contact"),
      cell: ({ row }) => (
        <div className="min-w-0">
          <p className="truncate text-[0.8125rem] text-foreground">{row.original.contact_name}</p>
          <p className="truncate type-caption text-muted-foreground">{row.original.contact_email}</p>
        </div>
      ),
    },
    {
      accessorKey: "created_at",
      header: t("submitted"),
      cell: ({ row }) => (
        <span className="whitespace-nowrap type-small text-muted-foreground">
          {formatDateTime(row.original.created_at, locale)}
        </span>
      ),
    },
    {
      accessorKey: "status",
      header: t("status"),
      cell: ({ row }) => (
        <StatusChip tone={STATUS_CHIP[row.original.status] ?? "neutral"} dot>
          {statusText(row.original)}
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
        <KpiRow cols={4}>
          <KpiTile label={t("filterPending")} value={allQuery.isPending ? "—" : String(countPending)} icon={Hourglass} />
          <KpiTile label={t("filterApproved")} value={allQuery.isPending ? "—" : String(countApproved)} icon={CheckCircle2} />
          <KpiTile label={t("filterRejected")} value={allQuery.isPending ? "—" : String(countRejected)} icon={XCircle} />
          <KpiTile label={t("kpiTotal")} value={allQuery.isPending ? "—" : String(allItems.length)} icon={ListChecks} />
        </KpiRow>

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
                onValueChange={setStatusFilter}
                size="sm"
                options={[
                  { value: "pending_review", label: t("filterPending") },
                  { value: "approved", label: t("filterApproved") },
                  { value: "rejected", label: t("filterRejected") },
                  { value: "all", label: t("filterAll") },
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
        subtitle={selected ? [selected.industry, selected.company_size].filter(Boolean).join(" · ") || undefined : undefined}
        closeLabel={tc("close")}
        avatar={
          <span className="flex size-10 items-center justify-center rounded-xl bg-[var(--viz-indigo-soft)]">
            <Building2 className="size-5 text-[var(--viz-indigo)]" strokeWidth={1.8} />
          </span>
        }
        status={
          selected ? (
            <StatusChip tone={STATUS_CHIP[selected.status] ?? "neutral"} dot>
              {statusText(selected)}
            </StatusChip>
          ) : undefined
        }
        footer={
          selected ? (
            isPending ? (
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
                    setTrustLevel("standard");
                    setApproveOpen(true);
                  }}
                >
                  <Check className="size-4" strokeWidth={2} />
                  {t("approve")}
                </Button>
              </>
            ) : selected.status === "approved" && selected.created_org_id ? (
              <Link href={`/university/partners/${selected.created_org_id}`}>
                <Button variant="secondary" size="sm">
                  <ExternalLink className="size-4" strokeWidth={1.8} />
                  {t("crmOpen")}
                </Button>
              </Link>
            ) : undefined
          ) : undefined
        }
      >
        {selected && (
          <>
            <DetailSheetSection title={t("detailTitle")}>
              <dl className="space-y-0.5">
                <DetailRow label={t("industry")}>{selected.industry || "—"}</DetailRow>
                <DetailRow label={t("companySize")}>{selected.company_size || "—"}</DetailRow>
                <DetailRow label={t("submitted")}>{formatDateTime(selected.created_at, locale)}</DetailRow>
              </dl>
            </DetailSheetSection>

            <DetailSheetSection title={t("contact")}>
              <dl className="space-y-0.5">
                <DetailRow label={t("contactName")}>{selected.contact_name}</DetailRow>
                <DetailRow label={t("contactTitle")}>{selected.contact_title || "—"}</DetailRow>
                <DetailRow label={t("email")}>{selected.contact_email}</DetailRow>
              </dl>
            </DetailSheetSection>

            {selected.review_note && (
              <DetailSheetSection title={t("reviewNote")}>
                <p className="text-[0.8125rem] text-foreground">{selected.review_note}</p>
              </DetailSheetSection>
            )}

            {!isPending && (
              <DetailSheetSection>
                <p className="type-small text-muted-foreground">{t("alreadyReviewed")}</p>
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
        <div className="space-y-4">
          <Select
            label={t("trustLevel")}
            help={t("trustLevelHelp")}
            value={trustLevel}
            onChange={(e) => setTrustLevel(e.target.value as TrustLevel)}
            options={[
              { value: "standard", label: t("trustStandard") },
              { value: "verified", label: t("trustVerified") },
              { value: "strategic", label: t("trustStrategic") },
            ]}
          />
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
