"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ChatCircleDots,
  Eye,
  LightbulbFilament,
  MagnifyingGlass,
  ShieldWarning,
  SignIn,
  Sparkle,
  UserFocus,
  WarningCircle,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, EmptyState, Modal, Skeleton, StatusBadge, Textarea, useToast } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { formatDateTime } from "@/lib/format";
import { APPLICATION_STATUS_TONE, useApplicationLabels } from "@/lib/applications/labels";
import { ApiError, applicationsApi, type RevealDecision } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { Meta } from "./application-detail/meta";
import { statusNextSteps, StatusTimeline } from "./application-detail/status-timeline";
import { NextActionBanner } from "./application-detail/next-action-banner";
import { UpcomingInterviewCard } from "./application-detail/upcoming-interview-card";
import { StudentOwnOfferCard } from "./application-detail/student-own-offer-card";

const WITHDRAW_REASON_MAX = 500;

export function StudentApplicationDetail({ id }: { id: string }) {
  const t = useTranslations("applications");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useApplicationLabels();
  const toast = useToast();
  const qc = useQueryClient();
  const apiError = useApiErrorMessage();

  const [confirmWithdraw, setConfirmWithdraw] = useState(false);
  const [withdrawReason, setWithdrawReason] = useState("");

  const query = useQuery({
    queryKey: ["applications", "detail", id],
    queryFn: () => applicationsApi.getMine(id),
    retry: false,
  });

  const app = query.data;

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["applications", "detail", id] });
    void qc.invalidateQueries({ queryKey: ["applications", "mine"] });
  }

  const withdraw = useMutation({
    mutationFn: () =>
      applicationsApi.withdraw(id, {
        version: app?.version,
        reason: withdrawReason.trim() ? withdrawReason.trim() : undefined,
      }),
    onSuccess: () => {
      setConfirmWithdraw(false);
      setWithdrawReason("");
      toast.show({ tone: "success", title: t("withdrawnToast") });
      refresh();
    },
    onError: (e) => {
      setConfirmWithdraw(false);
      if (e instanceof ApiError && e.isConflict) {
        toast.show({
          tone: "error",
          title: t("withdrawVersionConflictTitle"),
          description: t("withdrawVersionConflictBody"),
        });
        refresh();
        return;
      }
      toast.show({ tone: "error", title: apiError(e) });
    },
  });

  const respond = useMutation({
    mutationFn: (decision: RevealDecision) =>
      applicationsApi.respondReveal(id, decision),
    onSuccess: (_res, decision) => {
      toast.show({
        tone: decision === "accepted" ? "success" : "info",
        title:
          decision === "accepted"
            ? t("revealAcceptedToast")
            : t("revealDeclinedToast"),
      });
      refresh();
    },
    onError: (e) => toast.show({ tone: "error", title: apiError(e) }),
  });

  const backLink = (
    <Link
      href="/student/applications"
      className="mb-4 inline-flex items-center gap-1.5 rounded-lg text-sm font-medium text-[var(--text-secondary)] outline-none hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
    >
      <ArrowLeft aria-hidden weight="bold" className="size-4" />
      {t("backToList")}
    </Link>
  );

  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    const kind = err.isAuthError
      ? "auth"
      : err.isNotFound
        ? "empty"
        : "error";
    return (
      <>
        {backLink}
        <EmptyState
          kind={kind}
          icon={
            err.isAuthError
              ? SignIn
              : err.isNotFound
                ? MagnifyingGlass
                : WarningCircle
          }
          title={
            err.isAuthError
              ? tStates("authTitle")
              : err.isNotFound
                ? t("notFoundTitle")
                : tStates("errorTitle")
          }
          description={
            err.isAuthError
              ? tStates("authBody")
              : err.isNotFound
                ? t("notFoundBody")
                : tStates("errorBody")
          }
          action={
            err.isNotFound ? (
              <Link href="/student/applications">
                <Button variant="secondary">{t("backToList")}</Button>
              </Link>
            ) : !err.isAuthError ? (
              <Button variant="secondary" onClick={() => query.refetch()}>
                {tc("retry")}
              </Button>
            ) : undefined
          }
        />
      </>
    );
  }

  if (query.isPending || !app) {
    return (
      <>
        {backLink}
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="mt-3 h-4 w-1/3" />
        <Skeleton className="mt-6 h-40 w-full" />
      </>
    );
  }

  const canWithdraw =
    app.can_withdraw ?? (app.status === "submitted" || app.status === "under_review");
  const reveal = app.reveal_request;
  const screeningEntries = Object.entries(app.screening_answers ?? {});

  return (
    <>
      {backLink}
      <PageHeader title={app.job_title ?? t("untitledJob")} />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <StatusBadge tone={APPLICATION_STATUS_TONE[app.status] ?? "info"}>
          {labels.status(app.status, app.status_label)}
        </StatusBadge>
        {app.is_anonymous && (
          <StatusBadge tone="info">{t("anonymousBadge")}</StatusBadge>
        )}
      </div>

      {/* Honest "what happens next" callout driven by the server's next_action. */}
      <NextActionBanner nextAction={app.next_action} />

      {/* Decision-status timeline. Student projection carries status + the
          timestamp only — never the partner's rejection reason/note. */}
      <StatusTimeline
        status={app.status}
        statusLabel={app.status_label}
        lastStatusAt={app.last_status_at}
        timeline={app.timeline}
      />

      {/* AI Next Steps — derived from status, no API call. */}
      {(() => {
        const steps = statusNextSteps(app.status, t as (key: string) => string);
        if (steps.length === 0) return null;
        return (
          <div className="mb-6 rounded-2xl border border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-[var(--glass-surface-light)] p-4 backdrop-blur-xl">
            <div className="mb-3 flex items-center gap-2">
              <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-[var(--brand-primary)] to-[var(--brand-teal)] shadow-sm">
                <Sparkle aria-hidden weight="fill" className="size-3.5 text-white" />
              </span>
              <span className="text-sm font-bold text-[var(--text-primary)]">
                {t("aiNextStepsTitle")}
              </span>
            </div>
            <ul className="space-y-1.5">
              {steps.map((step, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-[var(--text-secondary)]">
                  <LightbulbFilament aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0 text-[var(--ai-accent)]" />
                  {step}
                </li>
              ))}
            </ul>
          </div>
        );
      })()}

      {/* The student's OWN offer card (ADR-0007). Identity-safe to the owner:
          position / their own comp / start / deadline + Accept/Decline. Surfaced
          only for a sent+terminal offer — never partner internals. */}
      {app.offer && (
        <StudentOwnOfferCard
          offer={app.offer}
          jobTitle={app.job_title}
          onResponded={refresh}
        />
      )}

      {/* The student's OWN upcoming interview (ADR-0006). Identity-safe by
          construction: date/mode/location-or-link/status only — NEVER assignee
          identities, scores, or the advance gate. */}
      {app.upcoming_interview && (
        <UpcomingInterviewCard interview={app.upcoming_interview} />
      )}

      {/* Real application-bound message thread — omitted entirely when none
          exists yet, never a fabricated empty "Messages" section. */}
      {app.messages_pointer && (
        <Link
          href={{
            pathname: "/student/messages",
            query: { thread: app.messages_pointer.thread_id },
          }}
          className="mb-6 flex items-center gap-3 rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-4 backdrop-blur-md outline-none transition hover:bg-[var(--bg-muted)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
        >
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg icon-chip-info shadow-sm">
            <ChatCircleDots aria-hidden weight="duotone" className="size-4 text-white" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {t("messagesPointerTitle")}
            </p>
            <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
              {t("messagesPointerUnread", { count: app.messages_pointer.unread_count })}
            </p>
          </div>
          <span className="shrink-0 text-sm font-medium text-[var(--brand-primary)]">
            {t("messagesPointerCta")}
          </span>
        </Link>
      )}

      {/* Pending reveal request — rendered only when the API surfaces it. */}
      {reveal && reveal.status === "pending" && (
        <div
          role="alert"
          className="mb-6 rounded-2xl border border-[var(--amber-600)]/40 bg-[var(--amber-100)] p-4"
        >
          <div className="flex items-start gap-3">
            <span className="flex size-7 shrink-0 items-center justify-center rounded-lg icon-chip-warning shadow-sm">
              <UserFocus aria-hidden weight="duotone" className="size-4 text-white" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {t("revealRequestTitle")}
              </p>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                {t("revealRequestBody")}
              </p>
              <blockquote className="mt-2 rounded-lg bg-[var(--glass-surface)] p-3 text-sm italic text-[var(--text-secondary)]">
                {reveal.reason}
              </blockquote>
              <p className="mt-2 text-xs text-[var(--text-muted)]">
                {t("revealExpires", {
                  date: formatDateTime(reveal.expires_at, locale),
                })}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button
                  variant="primary"
                  size="sm"
                  loading={respond.isPending}
                  onClick={() => respond.mutate("accepted")}
                >
                  {t("revealAccept")}
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={respond.isPending}
                  onClick={() => respond.mutate("declined")}
                >
                  {t("revealDecline")}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Submitted snapshot summary */}
      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Meta label={t("appliedAt")}>
          {formatDateTime(app.applied_at, locale)}
        </Meta>
        <Meta label={t("lastUpdate")}>
          {formatDateTime(app.last_status_at ?? app.updated_at, locale)}
        </Meta>
        <Meta label={t("cvSnapshot")}>
          <span className="inline-flex items-center gap-1.5">
            <Eye
              aria-hidden
              weight="duotone"
              className="size-4 text-[var(--text-muted)]"
            />
            {t("snapshotLocked")}
          </span>
        </Meta>
        <Meta label={t("visibilityToEmployer")}>
          {app.is_anonymous ? t("anonymousBadge") : t("identified")}
        </Meta>
      </dl>

      {app.cover_letter && (
        <section className="mt-6">
          <h2 className="mb-2 text-lg font-bold tracking-tight text-[var(--text-primary)]">
            {t("coverLetter")}
          </h2>
          <p className="whitespace-pre-wrap rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] backdrop-blur-md p-4 text-sm leading-relaxed text-[var(--text-secondary)]">
            {app.cover_letter}
          </p>
        </section>
      )}

      {screeningEntries.length > 0 && (
        <section className="mt-6">
          <h2 className="mb-2 text-lg font-bold tracking-tight text-[var(--text-primary)]">
            {t("yourAnswers")}
          </h2>
          <dl className="space-y-2">
            {screeningEntries.map(([key, value]) => (
              <div
                key={key}
                className="rounded-xl border border-[var(--glass-border)] bg-[var(--glass-surface)] backdrop-blur-md p-3"
              >
                <dt className="text-xs font-medium text-[var(--text-muted)]">
                  {key}
                </dt>
                <dd className="mt-0.5 text-sm text-[var(--text-primary)]">
                  {Array.isArray(value) ? value.join(", ") : value}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {/* Actions */}
      <div className="mt-8 flex flex-wrap gap-2">
        {app.job_title && (
          <Link href={`/jobs/${app.job_id}`}>
            <Button variant="secondary">{t("viewJob")}</Button>
          </Link>
        )}
        {canWithdraw && (
          <Button variant="danger" onClick={() => setConfirmWithdraw(true)}>
            {t("withdraw")}
          </Button>
        )}
        {app.status === "withdrawn" && (
          <p className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
            <ShieldWarning aria-hidden weight="duotone" className="size-4" />
            {t("withdrawnNote")}
          </p>
        )}
      </div>

      <Modal
        open={confirmWithdraw}
        onClose={() => setConfirmWithdraw(false)}
        title={t("withdrawConfirmTitle")}
        description={t("withdrawConfirmBody")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmWithdraw(false)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="danger"
              loading={withdraw.isPending}
              onClick={() => withdraw.mutate()}
            >
              {t("withdraw")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">
          {t("withdrawConfirmNote")}
        </p>
        <Textarea
          className="mt-3"
          label={t("withdrawReasonLabel")}
          placeholder={t("withdrawReasonPlaceholder")}
          value={withdrawReason}
          maxLength={WITHDRAW_REASON_MAX}
          rows={3}
          onChange={(e) => setWithdrawReason(e.target.value.slice(0, WITHDRAW_REASON_MAX))}
          help={t("withdrawReasonCounter", { count: withdrawReason.length })}
        />
      </Modal>
    </>
  );
}
