"use client";

import { useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Buildings,
  CheckCircle,
  XCircle,
  LightbulbFilament,
  ShieldWarning,
  SignIn,
  Hourglass,
  Sparkle,
  IdentificationBadge,
} from "@phosphor-icons/react";
import {
  Button,
  DataTable,
  EmptyState,
  Modal,
  Select,
  Sheet,
  StatusBadge,
  useToast,
  type Column,
  type StatusTone,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { cn } from "@/lib/utils";
import {
  ApiError,
  partnerApi,
  type PartnerRegistration,
  type TrustLevel,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { formatDateTime } from "@/lib/format";

const STATUS_TONE: Record<string, StatusTone> = {
  pending_review: "pending",
  approved: "accepted",
  rejected: "rejected",
};

const STATUS_LABEL_KEY: Record<string, string> = {
  pending_review: "filterPending",
  approved: "filterApproved",
  rejected: "filterRejected",
};

type ReviewInsightKey =
  | "insightManyPending"
  | "insightOnePending"
  | "insightAllResolved"
  | "insightGrowingNetwork"
  | "insightHighRejection";

function deriveReviewInsights(
  countPending: number,
  countApproved: number,
  countRejected: number,
): ReviewInsightKey[] {
  const out: ReviewInsightKey[] = [];
  const total = countPending + countApproved + countRejected;
  if (countPending > 3) out.push("insightManyPending");
  else if (countPending > 0) out.push("insightOnePending");
  if (countPending === 0 && total > 0) out.push("insightAllResolved");
  if (countApproved >= 10) out.push("insightGrowingNetwork");
  if (total > 5 && countRejected / total > 0.4) out.push("insightHighRejection");
  return out.slice(0, 2);
}

export function PartnerReviewScreen() {
  const t = useTranslations("partnersReview");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const [statusFilter, setStatusFilter] = useState<string>("pending_review");
  const [selected, setSelected] = useState<PartnerRegistration | null>(null);
  const [approveOpen, setApproveOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [trustLevel, setTrustLevel] = useState<TrustLevel>("standard");
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["admin", "partners", statusFilter],
    queryFn: () =>
      partnerApi.listRegistrations(statusFilter === "all" ? undefined : statusFilter),
    retry: false,
  });

  const allQuery = useQuery({
    queryKey: ["admin", "partners", "all", "counts"],
    queryFn: () => partnerApi.listRegistrations(),
    retry: false,
    staleTime: 30_000,
  });
  const allItems = allQuery.data ?? [];
  const countPending = allItems.filter((r) => r.status === "pending_review").length;
  const countApproved = allItems.filter((r) => r.status === "approved").length;
  const countRejected = allItems.filter((r) => r.status === "rejected").length;

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["admin", "partners"] });
  }

  const approve = useMutation({
    mutationFn: (reg: PartnerRegistration) =>
      partnerApi.approve(reg.id, {
        trust_level: trustLevel,
        note: note || null,
        version: reg.version,
      }),
    onSuccess: () => {
      setApproveOpen(false);
      setSelected(null);
      setNote("");
      toast.show({ tone: "success", title: t("approvedToast") });
      refresh();
    },
    onError: (e) => handleMutationError(e),
  });

  const reject = useMutation({
    mutationFn: (reg: PartnerRegistration) =>
      partnerApi.reject(reg.id, { reason, version: reg.version }),
    onSuccess: () => {
      setRejectOpen(false);
      setSelected(null);
      setReason("");
      toast.show({ tone: "success", title: t("rejectedToast") });
      refresh();
    },
    onError: (e) => handleMutationError(e),
  });

  function handleMutationError(e: unknown) {
    const reasonCode =
      e instanceof ApiError && typeof e.details?.reason === "string"
        ? e.details.reason
        : undefined;
    if (reasonCode === "version_conflict" || (e instanceof ApiError && e.code === "CONFLICT")) {
      toast.show({ tone: "error", title: t("conflictToast"), description: t("conflictBody") });
      setApproveOpen(false);
      setRejectOpen(false);
      setSelected(null);
      refresh();
      return;
    }
    toast.show({ tone: "error", title: getMessage(e) });
  }

  // 401 / 403 → dedicated states (frontend rule: permission state, not error).
  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError) {
      return (
        <>
          <PageHeader title={t("title")} description={t("subtitle")} />
          <EmptyState
            kind="permission"
            icon={ShieldWarning}
            title={tStates("permissionTitle")}
            description={t("permissionBody")}
          />
        </>
      );
    }
    if (err.isAuthError) {
      return (
        <>
          <PageHeader title={t("title")} description={t("subtitle")} />
          <EmptyState
            kind="auth"
            icon={SignIn}
            title={tStates("authTitle")}
            description={tStates("authBody")}
          />
        </>
      );
    }
  }

  const isError = query.isError;
  const rows = query.data ?? [];

  const columns: Column<PartnerRegistration>[] = [
    {
      key: "company_name",
      header: t("company"),
      cell: (r) => (
        <div className="flex items-center gap-2">
          <Buildings aria-hidden weight="duotone" className="size-5 text-[var(--text-muted)]" />
          <div className="min-w-0">
            <p className="truncate font-semibold text-[var(--text-primary)]">
              {r.company_name}
            </p>
            <p className="truncate text-xs text-[var(--text-secondary)]">
              {[r.industry, r.company_size].filter(Boolean).join(" · ") || "—"}
            </p>
          </div>
        </div>
      ),
    },
    {
      key: "contact",
      header: t("contact"),
      cell: (r) => (
        <div className="min-w-0">
          <p className="truncate text-[var(--text-primary)]">{r.contact_name}</p>
          <p className="truncate text-xs text-[var(--text-secondary)]">{r.contact_email}</p>
        </div>
      ),
    },
    {
      key: "created_at",
      header: t("submitted"),
      cell: (r) => formatDateTime(r.created_at, locale),
    },
    {
      key: "status",
      header: t("status"),
      cell: (r) => (
        <StatusBadge tone={STATUS_TONE[r.status] ?? "info"}>{statusText(r)}</StatusBadge>
      ),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      cell: (r) => (
        <div className="flex justify-end gap-1">
          {r.status === "approved" && r.created_org_id && (
            <Link
              href={`/university/partners/${r.created_org_id}`}
              className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold text-[var(--text-secondary)] outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
            >
              <IdentificationBadge aria-hidden weight="duotone" className="size-3.5" />
              {t("crmDetail")}
            </Link>
          )}
          <Button variant="ghost" size="sm" onClick={() => setSelected(r)}>
            {t("review")}
          </Button>
        </div>
      ),
    },
  ];

  const isPending = selected?.status === "pending_review";

  const statusText = (reg: PartnerRegistration) =>
    STATUS_LABEL_KEY[reg.status] ? t(STATUS_LABEL_KEY[reg.status]!) : reg.status_label;

  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />

      {/* Partner registration counts */}
      <div className="mb-5 grid grid-cols-3 gap-3">
        <div className="rounded-2xl border border-[var(--border-default)] bg-white px-4 py-4 shadow-[0_2px_16px_rgba(11,34,57,0.06)] transition-all hover:-translate-y-0.5">
          <div className="mb-3 flex size-10 items-center justify-center rounded-xl icon-chip-warning shadow-sm">
            <Hourglass aria-hidden weight="duotone" className="size-5 text-white" />
          </div>
          <p className="text-3xl font-black tracking-tight text-[var(--text-primary)]">
            {allQuery.isPending ? "—" : countPending}
          </p>
          <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("filterPending")}</p>
        </div>
        <div className="rounded-2xl border border-[var(--border-default)] bg-white px-4 py-4 shadow-[0_2px_16px_rgba(11,34,57,0.06)] transition-all hover:-translate-y-0.5">
          <div className="mb-3 flex size-10 items-center justify-center rounded-xl icon-chip-success shadow-sm">
            <CheckCircle aria-hidden weight="duotone" className="size-5 text-white" />
          </div>
          <p className="text-3xl font-black tracking-tight text-[var(--text-primary)]">
            {allQuery.isPending ? "—" : countApproved}
          </p>
          <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("filterApproved")}</p>
        </div>
        <div className="rounded-2xl border border-[var(--border-default)] bg-white px-4 py-4 shadow-[0_2px_16px_rgba(11,34,57,0.06)] transition-all hover:-translate-y-0.5">
          <div className="mb-3 flex size-10 items-center justify-center rounded-xl icon-chip-danger shadow-sm">
            <XCircle aria-hidden weight="duotone" className="size-5 text-white" />
          </div>
          <p className="text-3xl font-black tracking-tight text-[var(--text-primary)]">
            {allQuery.isPending ? "—" : countRejected}
          </p>
          <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("filterRejected")}</p>
        </div>
      </div>

      {/* AI Partner Review Insights */}
      {(() => {
        const insights = !allQuery.isPending ? deriveReviewInsights(countPending, countApproved, countRejected) : [];
        if (insights.length === 0) return null;
        return (
          <section
            className="mb-5 rounded-2xl border border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-white/60 p-4 "
            aria-label={t("aiInsightsTitle")}
          >
            <h2 className="mb-2.5 flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-info shadow-sm">
                <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
              </span>
              {t("aiInsightsTitle")}
            </h2>
            <ul className="space-y-1.5">
              {insights.map((key) => (
                <li key={key} className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                  <LightbulbFilament aria-hidden weight="duotone" className="mt-0.5 size-3.5 shrink-0 text-[var(--ai-accent)]" />
                  {t(key)}
                </li>
              ))}
            </ul>
          </section>
        );
      })()}

      {/* Status filter tab chips */}
      <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label={t("filterLabel")}>
        {[
          { value: "pending_review", label: t("filterPending"), activeClass: "bg-amber-500 border-amber-400/30 text-white" },
          { value: "approved", label: t("filterApproved"), activeClass: "bg-emerald-600 border-emerald-500/30 text-white" },
          { value: "rejected", label: t("filterRejected"), activeClass: "bg-red-600 border-red-500/30 text-white" },
          { value: "all", label: t("filterAll"), activeClass: "bg-[var(--brand-primary)] border-[var(--brand-primary)]/30 text-white" },
        ].map(({ value, label, activeClass }) => (
          <button
            key={value}
            onClick={() => setStatusFilter(value)}
            aria-pressed={statusFilter === value}
            className={cn(
              "inline-flex items-center rounded-full border px-3.5 py-1.5 text-xs font-semibold transition-all focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-primary)]",
              statusFilter === value
                ? `${activeClass} shadow-sm`
                : "border-[var(--border-default)] bg-white text-[var(--text-secondary)] hover:bg-white hover:text-[var(--text-primary)]",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {isError ? (
        <EmptyState
          kind="error"
          icon={ShieldWarning}
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
          rows={rows}
          getRowId={(r) => r.id}
          loading={query.isPending}
          caption={t("title")}
          empty={{
            kind: "empty",
            icon: Buildings,
            title: t("empty"),
            description: t("emptyBody"),
          }}
        />
      )}

      {/* Detail drawer */}
      <Sheet
        open={selected !== null && !approveOpen && !rejectOpen}
        onClose={() => setSelected(null)}
        title={t("detailTitle")}
        closeLabel={tc("close")}
      >
        {selected && (
          <div className="space-y-4">
            <Field label={t("company")} value={selected.company_name} />
            <Field label={t("industry")} value={selected.industry} />
            <Field label={t("companySize")} value={selected.company_size} />
            <Field label={t("contactName")} value={selected.contact_name} />
            <Field label={t("contactTitle")} value={selected.contact_title} />
            <Field label={t("email")} value={selected.contact_email} />
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                {t("status")}
              </p>
              <div className="mt-1">
                <StatusBadge tone={STATUS_TONE[selected.status] ?? "info"}>
                  {statusText(selected)}
                </StatusBadge>
              </div>
            </div>
            {selected.review_note && (
              <Field label={t("reviewNote")} value={selected.review_note} />
            )}

            {isPending ? (
              <div className="flex flex-col gap-2 pt-2">
                <Button
                  variant="primary"
                  fullWidth
                  onClick={() => {
                    setTrustLevel("standard");
                    setApproveOpen(true);
                  }}
                >
                  <CheckCircle aria-hidden weight="bold" className="size-4" />
                  {t("approve")}
                </Button>
                <Button
                  variant="danger"
                  fullWidth
                  onClick={() => {
                    setReason("");
                    setReasonError(null);
                    setRejectOpen(true);
                  }}
                >
                  <XCircle aria-hidden weight="bold" className="size-4" />
                  {t("reject")}
                </Button>
              </div>
            ) : (
              <p className="rounded-xl border border-[var(--border-default)] bg-white px-3 py-2 text-sm text-[var(--text-secondary)] ">
                {t("alreadyReviewed")}
              </p>
            )}
          </div>
        )}
      </Sheet>

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
            <Button
              variant="primary"
              loading={approve.isPending}
              onClick={() => selected && approve.mutate(selected)}
            >
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
          <div>
            <label
              htmlFor="approve-note"
              className="mb-1.5 block text-sm font-semibold text-[var(--text-primary)]"
            >
              {t("noteOptional")}
            </label>
            <textarea
              id="approve-note"
              rows={3}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              className="w-full rounded-xl border border-[var(--border-default)] bg-white px-3.5 py-2.5 text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--brand-primary)]/50 focus:bg-white focus:ring-2 focus:ring-[var(--brand-primary)]/30"
            />
          </div>
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
        <div>
          <label
            htmlFor="reject-reason"
            className="mb-1.5 block text-sm font-semibold text-[var(--text-primary)]"
          >
            {t("reason")}
            <span className="ml-0.5 text-[var(--brand-red)]" aria-hidden>
              *
            </span>
          </label>
          <textarea
            id="reject-reason"
            rows={3}
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
              if (reasonError) setReasonError(null);
            }}
            aria-invalid={reasonError ? true : undefined}
            className="w-full rounded-xl border border-[var(--border-default)] bg-white px-3.5 py-2.5 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--brand-primary)]/50 focus:bg-white focus:ring-2 focus:ring-[var(--brand-primary)]/30"
          />
          {reasonError && (
            <p className="mt-1 text-xs font-medium text-[var(--brand-red)]">{reasonError}</p>
          )}
        </div>
      </Modal>
    </>
  );
}

function Field({ label, value }: { label: string; value?: string | null }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {label}
      </p>
      <p className="mt-0.5 text-sm text-[var(--text-primary)]">{value || "—"}</p>
    </div>
  );
}
