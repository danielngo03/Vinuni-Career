"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  Lightning,
  Plus,
  WarningCircle,
  Sparkle,
  HourglassMedium,
} from "@phosphor-icons/react";
import { Button, EmptyState, Skeleton, StatusBadge } from "@/components/ui";
import { aiAssistantApi, aiGovernanceApi, type AiCapacityRequest } from "@/lib/api";
import { CapacityRequestDialog } from "./capacity-request-dialog";
import { capacityStatusTone, formatDateTime, formatCredits } from "./helpers";

/**
 * University staff "My AI capacity" view. Shows whether the caller is
 * energy-limited or unlimited, lets them request more capacity (distribution,
 * not billing), and lists their own requests with live status. Rendered in the
 * university settings shell. Energy is opaque credits only.
 */
export function MyAiCapacitySection() {
  const t = useTranslations("aiGovernance.staff");
  const tStatus = useTranslations("aiGovernance.status");
  const locale = useLocale();
  const [dialogOpen, setDialogOpen] = useState(false);

  const usage = useQuery({
    queryKey: ["ai", "usage", "me"],
    queryFn: () => aiAssistantApi.myUsage(),
    staleTime: 60_000,
    retry: false,
  });

  const requests = useQuery({
    queryKey: ["ai", "capacity-requests", "me"],
    queryFn: () => aiGovernanceApi.myCapacityRequests(),
    staleTime: 30_000,
    retry: 1,
  });

  const unlimited = usage.data?.unlimited ?? false;
  const rows = requests.data ?? [];
  const hasPending = rows.some((r) => r.status === "pending");

  // Superadmin / uncapped: nothing to request.
  if (unlimited) {
    return (
      <section aria-label={t("title")}>
        <Header t={t} />
        <EmptyState
          kind="empty"
          icon={Sparkle}
          title={t("unlimitedTitle")}
          description={t("unlimitedBody")}
        />
      </section>
    );
  }

  return (
    <section aria-label={t("title")} className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <Header t={t} />
        <Button
          variant="primary"
          onClick={() => setDialogOpen(true)}
          disabled={hasPending}
        >
          <Plus aria-hidden weight="bold" className="size-4" />
          {t("requestButton")}
        </Button>
      </div>

      {hasPending && (
        <div className="flex items-center gap-2 rounded-xl border border-[var(--amber-400)]/50 bg-[var(--amber-50)] px-3.5 py-2.5 text-sm font-medium text-[var(--amber-700)]">
          <HourglassMedium aria-hidden weight="fill" className="size-4 shrink-0" />
          {t("pendingBanner")}
        </div>
      )}

      {requests.isPending ? (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full rounded-2xl" />
          <Skeleton className="h-24 w-full rounded-2xl" />
        </div>
      ) : requests.isError ? (
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("errorTitle")}
          description={t("errorBody")}
          action={
            <Button variant="secondary" onClick={() => void requests.refetch()}>
              {t("retry")}
            </Button>
          }
        />
      ) : rows.length === 0 ? (
        <EmptyState
          kind="empty"
          icon={Lightning}
          title={t("emptyTitle")}
          description={t("emptyBody")}
        />
      ) : (
        <ul className="space-y-3">
          {rows.map((r) => (
            <RequestCard
              key={r.id}
              request={r}
              locale={locale}
              t={t}
              statusLabel={tStatus(r.status)}
            />
          ))}
        </ul>
      )}

      <CapacityRequestDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
      />
    </section>
  );
}

function Header({ t }: { t: ReturnType<typeof useTranslations<"aiGovernance.staff">> }) {
  return (
    <div>
      <h2 className="flex items-center gap-2 text-base font-bold tracking-tight text-[var(--text-primary)]">
        <span className="icon-chip-primary flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm">
          <Lightning aria-hidden weight="duotone" className="size-4" />
        </span>
        {t("title")}
      </h2>
      <p className="mt-1 max-w-prose text-sm text-[var(--text-secondary)]">
        {t("subtitle")}
      </p>
    </div>
  );
}

function RequestCard({
  request,
  locale,
  t,
  statusLabel,
}: {
  request: AiCapacityRequest;
  locale: string;
  t: ReturnType<typeof useTranslations<"aiGovernance.staff">>;
  statusLabel: string;
}) {
  const submitted = formatDateTime(request.created_at, locale);
  const decided = formatDateTime(request.decided_at, locale);

  return (
    <li className="rounded-2xl border border-[var(--border-default)] bg-white p-4 shadow-[0_2px_12px_rgba(11,34,57,0.05)]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <StatusBadge tone={capacityStatusTone(request.status)}>
            {statusLabel}
          </StatusBadge>
          {submitted && (
            <p className="mt-1.5 text-xs text-[var(--text-muted)]">
              {t("submittedAt", { when: submitted })}
            </p>
          )}
        </div>
        <div className="shrink-0 text-right">
          <p className="text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("requestedLabel")}
          </p>
          <p className="text-sm font-semibold tabular-nums text-[var(--text-primary)]">
            {request.requested_units != null
              ? t("creditsValue", {
                  units: formatCredits(request.requested_units, locale),
                })
              : t("creditsUnset")}
          </p>
        </div>
      </div>

      <p className="mt-3 text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {t("reasonLabel")}
      </p>
      <p className="mt-0.5 whitespace-pre-wrap break-words text-sm text-[var(--text-secondary)]">
        {request.reason}
      </p>

      {request.status !== "pending" && (request.decision_note || decided) && (
        <div className="mt-3 border-t border-[var(--border-default)] pt-3">
          <p className="text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("decisionLabel")}
          </p>
          {request.decision_note && (
            <p className="mt-0.5 whitespace-pre-wrap break-words text-sm text-[var(--text-secondary)]">
              {request.decision_note}
            </p>
          )}
          {decided && (
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              {t("decidedAt", { when: decided })}
            </p>
          )}
        </div>
      )}
    </li>
  );
}
