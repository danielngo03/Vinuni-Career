"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ShieldWarning,
  SignIn,
  LockKey,
  FileText,
  Download,
  Trash,
  Clock,
} from "@phosphor-icons/react";
import { Button, EmptyState, Skeleton, Switch, StatusBadge, useToast } from "@/components/ui";
import { SectionCard } from "./section-card";
import {
  ApiError,
  privacyApi,
  type ConsentType,
  type PrivacyRequestType,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { formatDateTime } from "@/lib/format";
import type { StatusTone } from "@/components/ui";

const CONSENT_TYPES: ConsentType[] = ["interview_recording", "career_outcomes_data_sharing"];

const REQUEST_STATUS_TONE: Record<string, StatusTone> = {
  pending: "pending",
  processing: "pending",
  fulfilled: "verified",
  rejected: "rejected",
};

/**
 * Student/self-service privacy tab (ADR-0014 §Privacy & Compliance).
 * Consent toggles (2 fixed types), read-only retention text, and data
 * export/deletion requests — all "own account" endpoints, shared across
 * personas since consents are not student-only.
 */
export function PrivacyTab() {
  const t = useTranslations("settings.privacy");
  const tStates = useTranslations("states");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const [pendingRequestType, setPendingRequestType] = useState<PrivacyRequestType | null>(null);

  const consentsQuery = useQuery({
    queryKey: ["account", "privacy", "consents"],
    queryFn: () => privacyApi.getConsents(),
    retry: false,
  });

  const retentionQuery = useQuery({
    queryKey: ["account", "privacy", "retention", locale],
    queryFn: () => privacyApi.getRetention(locale),
    retry: false,
  });

  const requestsQuery = useQuery({
    queryKey: ["account", "privacy", "requests"],
    queryFn: () => privacyApi.listMyRequests(),
    retry: false,
  });

  const setConsent = useMutation({
    mutationFn: ({ type, granted }: { type: ConsentType; granted: boolean }) =>
      privacyApi.setConsent(type, granted),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["account", "privacy", "consents"] });
    },
    onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
  });

  const submitRequest = useMutation({
    mutationFn: (type: PrivacyRequestType) => privacyApi.submitRequest(type),
    onSuccess: (res) => {
      setPendingRequestType(null);
      void qc.invalidateQueries({ queryKey: ["account", "privacy", "requests"] });
      toast.show({
        tone: "success",
        title:
          res.status === "request_already_pending"
            ? t("requestAlreadyPending")
            : t("requestSubmitted"),
      });
    },
    onError: (e) => {
      setPendingRequestType(null);
      toast.show({ tone: "error", title: getMessage(e) });
    },
  });

  function onRequest(type: PrivacyRequestType) {
    setPendingRequestType(type);
    submitRequest.mutate(type);
  }

  const isAuthErr = (q: { error: unknown }) =>
    q.error instanceof ApiError && q.error.isAuthError;

  return (
    <>
      <SectionCard
        title={t("consentsTitle")}
        description={t("consentsIntro")}
        icon={LockKey}
        iconGradient="icon-chip-info"
        className="mb-5"
      >
        {consentsQuery.isPending ? (
          <div className="space-y-3">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : consentsQuery.isError ? (
          <EmptyState
            kind={isAuthErr(consentsQuery) ? "auth" : "offline"}
            icon={isAuthErr(consentsQuery) ? SignIn : ShieldWarning}
            title={isAuthErr(consentsQuery) ? tStates("authTitle") : tStates("offlineTitle")}
            description={isAuthErr(consentsQuery) ? tStates("authBody") : tStates("offlineBody")}
            action={
              <Button variant="secondary" onClick={() => consentsQuery.refetch()}>
                {tCommon("retry")}
              </Button>
            }
          />
        ) : (
          <div className="space-y-4">
            {CONSENT_TYPES.map((type) => {
              const state = consentsQuery.data?.[type];
              return (
                <div
                  key={type}
                  className="flex items-start justify-between gap-4 rounded-xl border border-[var(--border-default)] bg-[var(--bg-subtle)] px-4 py-3"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-[var(--text-primary)]">
                      {t(`consentType.${type}.label`)}
                    </p>
                    <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                      {t(`consentType.${type}.description`)}
                    </p>
                    {state?.granted && state.granted_at && (
                      <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                        {t("grantedAt", { date: formatDateTime(state.granted_at, locale) })}
                      </p>
                    )}
                    {!state?.granted && state?.revoked_at && (
                      <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                        {t("revokedAt", { date: formatDateTime(state.revoked_at, locale) })}
                      </p>
                    )}
                  </div>
                  <Switch
                    id={`consent-${type}`}
                    checked={state?.granted ?? false}
                    disabled={setConsent.isPending}
                    onCheckedChange={(granted) => setConsent.mutate({ type, granted })}
                    label={t(`consentType.${type}.label`)}
                    hideLabel
                  />
                </div>
              );
            })}
          </div>
        )}
      </SectionCard>

      <SectionCard
        title={t("retentionTitle")}
        icon={Clock}
        iconGradient="icon-chip-neutral"
        className="mb-5"
      >
        {retentionQuery.isPending ? (
          <Skeleton className="h-16 w-full" />
        ) : retentionQuery.isError ? (
          <p className="text-sm text-[var(--text-secondary)]">{tStates("offlineBody")}</p>
        ) : (
          <ul className="space-y-2">
            {(retentionQuery.data ?? []).map((policy) => (
              <li key={policy.key} className="text-sm leading-6 text-[var(--text-secondary)]">
                {policy.label}
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      <SectionCard title={t("requestsTitle")} description={t("requestsIntro")} icon={FileText} iconGradient="icon-chip-warning">
        <div className="mb-5 flex flex-wrap gap-3">
          <Button
            variant="secondary"
            loading={submitRequest.isPending && pendingRequestType === "export"}
            disabled={submitRequest.isPending}
            onClick={() => onRequest("export")}
          >
            <Download aria-hidden weight="duotone" className="size-4" />
            {t("requestExport")}
          </Button>
          <Button
            variant="danger"
            loading={submitRequest.isPending && pendingRequestType === "deletion"}
            disabled={submitRequest.isPending}
            onClick={() => onRequest("deletion")}
          >
            <Trash aria-hidden weight="duotone" className="size-4" />
            {t("requestDeletion")}
          </Button>
        </div>

        {requestsQuery.isPending ? (
          <Skeleton className="h-20 w-full" />
        ) : requestsQuery.isError ? (
          <p className="text-sm text-[var(--text-secondary)]">{tStates("offlineBody")}</p>
        ) : (requestsQuery.data ?? []).length === 0 ? (
          <p className="text-sm text-[var(--text-muted)]">{t("noRequests")}</p>
        ) : (
          <ul className="space-y-2">
            {(requestsQuery.data ?? []).map((r) => (
              <li
                key={r.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--border-default)] bg-white px-4 py-3"
              >
                <div>
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    {t(`requestType.${r.request_type}`)}
                  </p>
                  <p className="text-xs text-[var(--text-muted)]">
                    {formatDateTime(r.created_at, locale)}
                  </p>
                </div>
                <StatusBadge tone={REQUEST_STATUS_TONE[r.status] ?? "info"}>
                  {t(`requestStatus.${r.status}`)}
                </StatusBadge>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </>
  );
}
