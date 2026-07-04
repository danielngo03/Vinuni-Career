"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle,
  ShieldWarning,
  SignIn,
  WarningCircle,
  XCircle,
  Envelope,
} from "@phosphor-icons/react";
import {
  Button,
  DataTable,
  EmptyState,
  Modal,
  StatusBadge,
  Textarea,
  useToast,
  type Column,
  type StatusTone,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { TrustTabs } from "./trust-tabs";
import { ApiError, privacyAdminApi, type PrivacyRequest } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { formatDateTime } from "@/lib/format";

const STATUS_FILTERS = ["pending", "processing", "fulfilled", "rejected"] as const;

const STATUS_TONE: Record<string, StatusTone> = {
  pending: "pending",
  processing: "pending",
  fulfilled: "verified",
  rejected: "rejected",
};

/**
 * Privacy/compliance admin queue (ADR-0014). Staff manually fulfill export/
 * deletion requests after performing the export/deletion out-of-band (V1 has
 * no orchestrated auto-purge engine) — this screen tracks lifecycle state and
 * the audited fulfill/reject decision, not the export/deletion mechanics
 * themselves.
 */
export function PrivacyAdminScreen() {
  const t = useTranslations("privacyAdmin");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");
  const locale = useLocale();
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const [statusFilter, setStatusFilter] = useState<string>("pending");
  const [target, setTarget] = useState<PrivacyRequest | null>(null);
  const [decision, setDecision] = useState<"fulfilled" | "rejected" | null>(null);
  const [note, setNote] = useState("");

  const query = useQuery({
    queryKey: ["privacy-admin", "requests", statusFilter],
    queryFn: () => privacyAdminApi.listRequests(statusFilter || undefined),
    retry: false,
  });

  const fulfill = useMutation({
    mutationFn: () => privacyAdminApi.fulfill(target!.id, decision!, note.trim() || undefined),
    onSuccess: () => {
      toast.show({
        tone: "success",
        title: decision === "fulfilled" ? t("fulfilledToast") : t("rejectedToast"),
      });
      setTarget(null);
      setDecision(null);
      setNote("");
      void qc.invalidateQueries({ queryKey: ["privacy-admin", "requests"] });
    },
    onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
  });

  const columns: Column<PrivacyRequest>[] = [
    {
      key: "request_type",
      header: t("colType"),
      cell: (r) => (
        <span className="inline-flex items-center gap-1.5 font-semibold text-[var(--text-primary)]">
          <Envelope aria-hidden weight="duotone" className="size-4 text-[var(--text-muted)]" />
          {t(`requestType.${r.request_type}`)}
        </span>
      ),
    },
    {
      key: "status",
      header: t("colStatus"),
      cell: (r) => <StatusBadge tone={STATUS_TONE[r.status] ?? "info"}>{t(`status.${r.status}`)}</StatusBadge>,
    },
    { key: "note", header: t("colNote"), cell: (r) => r.note || "—" },
    {
      key: "created_at",
      header: t("colSubmitted"),
      cell: (r) => formatDateTime(r.created_at, locale),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      cell: (r) =>
        r.status === "pending" || r.status === "processing" ? (
          <div className="flex justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setTarget(r);
                setDecision("fulfilled");
                setNote("");
              }}
            >
              <CheckCircle aria-hidden weight="bold" className="size-4" />
              {t("fulfill")}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setTarget(r);
                setDecision("rejected");
                setNote("");
              }}
            >
              <XCircle aria-hidden weight="bold" className="size-4" />
              {t("reject")}
            </Button>
          </div>
        ) : null,
    },
  ];

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
          <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label={t("filterLabel")}>
            {STATUS_FILTERS.map((s) => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                aria-pressed={statusFilter === s}
                className={
                  statusFilter === s
                    ? "rounded-full bg-[var(--text-primary)] px-3.5 py-1.5 text-xs font-semibold text-white"
                    : "rounded-full border border-[var(--border-default)] bg-white px-3.5 py-1.5 text-xs font-semibold text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                }
              >
                {t(`status.${s}`)}
              </button>
            ))}
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
              empty={{ kind: "empty", icon: Envelope, title: t("empty") }}
            />
          )}
        </>
      )}

      <Modal
        open={target !== null}
        onClose={() => {
          setTarget(null);
          setDecision(null);
        }}
        title={decision === "fulfilled" ? t("fulfillTitle") : t("rejectTitle")}
        description={t("decisionBody")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => {
                setTarget(null);
                setDecision(null);
              }}
            >
              {tc("cancel")}
            </Button>
            <Button
              variant={decision === "rejected" ? "danger" : "primary"}
              loading={fulfill.isPending}
              onClick={() => fulfill.mutate()}
            >
              {decision === "fulfilled" ? t("fulfillConfirm") : t("rejectConfirm")}
            </Button>
          </>
        }
      >
        <Textarea label={t("noteLabel")} value={note} onChange={(e) => setNote(e.target.value)} rows={3} />
      </Modal>
    </div>
  );
}
