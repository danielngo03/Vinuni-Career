"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowBendUpRight,
  ArrowCounterClockwise,
  ShieldWarning,
  SignIn,
  WarningCircle,
  Flag,
} from "@phosphor-icons/react";
import {
  Button,
  DataTable,
  EmptyState,
  Modal,
  Select,
  StatusBadge,
  Textarea,
  useToast,
  type Column,
  type StatusTone,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { TrustTabs } from "./trust-tabs";
import {
  ApiError,
  abuseApi,
  TRIAGE_SOURCES,
  type TriageItem,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { formatDateTime } from "@/lib/format";

const SEVERITY_TONE: Record<string, StatusTone> = {
  low: "info",
  medium: "pending",
  high: "rejected",
};

/**
 * Merged abuse/fraud triage queue (ADR-0014 §Abuse & Content Reports):
 * `content_reports` (pending/triaged) + `human_review_queue` (all sources),
 * sorted server-side by severity/recency. Escalate promotes a raw user
 * report into a review item; override reverses a prior moderation action and
 * is the one write path with a real before/after audit diff (surfaced here
 * as the known resource-side transition when one exists — see
 * `abuseApi.overrideAction` doc comment for the API-shape caveat).
 */
export function AbuseTriageScreen() {
  const t = useTranslations("abuseTriage");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");
  const locale = useLocale();
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const [source, setSource] = useState<string>("");
  const [escalateTarget, setEscalateTarget] = useState<TriageItem | null>(null);
  const [overrideTarget, setOverrideTarget] = useState<TriageItem | null>(null);
  const [note, setNote] = useState("");
  const [noteError, setNoteError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["abuse", "triage", source],
    queryFn: () => abuseApi.listTriage(source || undefined),
    retry: false,
  });

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["abuse", "triage"] });
  }

  const escalate = useMutation({
    mutationFn: (item: TriageItem) => abuseApi.escalateReport(item.id),
    onSuccess: () => {
      setEscalateTarget(null);
      toast.show({ tone: "success", title: t("escalatedToast") });
      refresh();
    },
    onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
  });

  const override = useMutation({
    mutationFn: () => abuseApi.overrideAction(overrideTarget!.id, note),
    onSuccess: () => {
      setOverrideTarget(null);
      setNote("");
      toast.show({ tone: "success", title: t("overriddenToast") });
      refresh();
    },
    onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
  });

  const columns: Column<TriageItem>[] = [
    {
      key: "kind",
      header: t("colKind"),
      cell: (r) => (
        <StatusBadge tone={r.kind === "content_report" ? "pending" : "info"}>
          {r.kind === "content_report" ? t("kindReport") : t("kindReviewItem")}
        </StatusBadge>
      ),
    },
    {
      key: "target",
      header: t("colTarget"),
      cell: (r) =>
        r.kind === "content_report" ? (
          <div className="min-w-0">
            <p className="font-semibold text-[var(--text-primary)]">{r.entity_type}</p>
            <p className="truncate text-xs text-[var(--text-muted)]">{r.reason_code}</p>
          </div>
        ) : (
          <div className="min-w-0">
            <p className="font-semibold text-[var(--text-primary)]">
              {r.resource_type ?? "—"}
            </p>
            <p className="truncate text-xs text-[var(--text-muted)]">{t(`source.${r.source}`)}</p>
          </div>
        ),
    },
    {
      key: "severity",
      header: t("colSeverity"),
      cell: (r) =>
        r.kind === "human_review_item" ? (
          <StatusBadge tone={SEVERITY_TONE[r.severity] ?? "info"}>
            {["low", "medium", "high"].includes(r.severity) ? t(`severity.${r.severity}`) : r.severity}
          </StatusBadge>
        ) : (
          <span className="text-[var(--text-muted)]">—</span>
        ),
    },
    { key: "status", header: t("colStatus"), cell: (r) => r.status },
    {
      key: "created_at",
      header: t("colCreated"),
      cell: (r) => formatDateTime(r.created_at, locale),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      cell: (r) => (
        <div className="flex justify-end gap-2">
          {r.kind === "content_report" && (r.status === "PENDING" || r.status === "TRIAGED") && (
            <Button variant="ghost" size="sm" onClick={() => setEscalateTarget(r)}>
              <ArrowBendUpRight aria-hidden weight="bold" className="size-4" />
              {t("escalate")}
            </Button>
          )}
          {r.kind === "human_review_item" && r.status === "pending" && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setOverrideTarget(r);
                setNote("");
                setNoteError(null);
              }}
            >
              <ArrowCounterClockwise aria-hidden weight="bold" className="size-4" />
              {t("override")}
            </Button>
          )}
        </div>
      ),
    },
  ];

  const overrideItem = overrideTarget?.kind === "human_review_item" ? overrideTarget : null;
  const hasKnownReversal = overrideItem?.resource_type === "user";

  return (
    <div>
      <PageHeader title={t("title")} />
      <TrustTabs />

      {query.isError && query.error instanceof ApiError && (query.error.isPermissionError || query.error.isAuthError) ? (
        <EmptyState
          kind={query.error.isPermissionError ? "permission" : "auth"}
          icon={query.error.isPermissionError ? ShieldWarning : SignIn}
          title={query.error.isPermissionError ? tStates("permissionTitle") : tStates("authTitle")}
          description={query.error.isPermissionError ? tStates("permissionBody") : tStates("authBody")}
        />
      ) : (
        <>
          <div className="mb-4 max-w-xs">
            <Select
              label={t("sourceLabel")}
              value={source}
              onChange={(e) => setSource(e.target.value)}
              options={[
                { value: "", label: t("sourceAll") },
                ...TRIAGE_SOURCES.map((s) => ({ value: s, label: t(`source.${s}`) })),
              ]}
            />
          </div>

          {query.isError ? (
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
            <DataTable
              columns={columns}
              rows={query.data ?? []}
              getRowId={(r) => r.id}
              loading={query.isPending}
              caption={t("title")}
              empty={{ kind: "empty", icon: Flag, title: t("empty") }}
            />
          )}
        </>
      )}

      {/* Escalate confirm */}
      <Modal
        open={escalateTarget !== null}
        onClose={() => setEscalateTarget(null)}
        title={t("escalateTitle")}
        description={t("escalateBody")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setEscalateTarget(null)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="primary"
              loading={escalate.isPending}
              onClick={() => escalateTarget && escalate.mutate(escalateTarget)}
            >
              {t("escalateConfirm")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">{t("escalateNote")}</p>
      </Modal>

      {/* Override with before/after diff */}
      <Modal
        open={overrideTarget !== null}
        onClose={() => setOverrideTarget(null)}
        title={t("overrideTitle")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setOverrideTarget(null)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="danger"
              loading={override.isPending}
              onClick={() => {
                if (!note.trim()) {
                  setNoteError(t("noteRequired"));
                  return;
                }
                override.mutate();
              }}
            >
              {t("overrideConfirm")}
            </Button>
          </>
        }
      >
        <div className="mb-4 rounded-xl border border-[var(--border-default)] bg-[var(--bg-subtle)] p-3">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("diffLabel")}
          </p>
          {hasKnownReversal ? (
            <div className="flex items-center gap-2 text-sm">
              <StatusBadge tone="rejected">{t("diffBefore")}</StatusBadge>
              <span aria-hidden>→</span>
              <StatusBadge tone="verified">{t("diffAfter")}</StatusBadge>
            </div>
          ) : (
            <p className="text-sm text-[var(--text-secondary)]">{t("diffUnavailable")}</p>
          )}
        </div>
        <Textarea
          label={t("noteLabel")}
          required
          value={note}
          onChange={(e) => {
            setNote(e.target.value);
            if (e.target.value.trim()) setNoteError(null);
          }}
          error={noteError ?? undefined}
          rows={3}
        />
        <p className="mt-3 rounded-xl border border-[var(--border-default)] bg-[var(--bg-subtle)] px-3 py-2 text-xs text-[var(--text-muted)]">
          {t("loggedNotice")}
        </p>
      </Modal>
    </div>
  );
}
