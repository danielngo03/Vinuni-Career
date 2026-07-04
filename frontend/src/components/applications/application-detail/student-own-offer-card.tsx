"use client";

import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import { Handshake, SealCheck, ShieldWarning } from "@phosphor-icons/react";
import { Button, Modal, StatusBadge, Textarea, useToast } from "@/components/ui";
import { formatDateTime } from "@/lib/format";
import { OFFER_STATUS_TONE, useOfferLabels } from "@/lib/applications/labels";
import {
  ApiError,
  applicationsApi,
  type StudentOfferCard as StudentOfferCardData,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { Meta } from "./meta";

/** Remaining-time bucket for a response deadline (minute granularity). */
function useCountdown(deadlineIso: string | null): {
  expired: boolean;
  days: number;
  hours: number;
  minutes: number;
} {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    // Tick once a minute — enough for a response deadline; calm for aria-live.
    const id = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(id);
  }, []);

  if (!deadlineIso) {
    return { expired: false, days: 0, hours: 0, minutes: 0 };
  }
  const target = new Date(deadlineIso).getTime();
  if (Number.isNaN(target)) {
    return { expired: false, days: 0, hours: 0, minutes: 0 };
  }
  const diff = target - now;
  if (diff <= 0) return { expired: true, days: 0, hours: 0, minutes: 0 };
  const minutesTotal = Math.floor(diff / 60_000);
  return {
    expired: false,
    days: Math.floor(minutesTotal / 1440),
    hours: Math.floor((minutesTotal % 1440) / 60),
    minutes: minutesTotal % 60,
  };
}

/**
 * The candidate's OWN offer card. The student is the owner, so their comp is
 * theirs to see (`comp_summary`); this surface NEVER carries partner internals
 * (`approved_by`, `decline_reason`) — those are not in the projection. Accept /
 * Decline go through a double-confirm modal (PRD "accept_offer (double confirm)").
 */
export function StudentOwnOfferCard({
  offer,
  jobTitle,
  onResponded,
}: {
  offer: StudentOfferCardData;
  jobTitle: string | null;
  onResponded: () => void;
}) {
  const t = useTranslations("applications");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useOfferLabels();
  const toast = useToast();
  const apiError = useApiErrorMessage();

  const [confirm, setConfirm] = useState<"accepted" | "declined" | null>(null);
  const [declineNote, setDeclineNote] = useState("");

  const countdown = useCountdown(offer.expiry_date);
  const isSent = offer.status === "sent";
  const actionable = isSent && !countdown.expired;

  const respond = useMutation({
    mutationFn: (decision: "accepted" | "declined") =>
      applicationsApi.respondOffer(offer.id, {
        decision,
        note: decision === "declined" ? declineNote.trim() || undefined : undefined,
      }),
    onSuccess: (_res, decision) => {
      setConfirm(null);
      setDeclineNote("");
      toast.show({
        tone: decision === "accepted" ? "success" : "info",
        title:
          decision === "accepted"
            ? t("offerAcceptedToast")
            : t("offerDeclinedToast"),
      });
      onResponded();
    },
    onError: (e) => {
      setConfirm(null);
      // The offer expired/terminal between render and click → friendly state.
      if (
        e instanceof ApiError &&
        e.isConflict &&
        e.details?.reason === "offer_not_actionable"
      ) {
        toast.show({ tone: "warning", title: t("offerNotActionableToast") });
        onResponded();
        return;
      }
      toast.show({ tone: "error", title: apiError(e) });
    },
  });

  const countdownLabel = countdown.expired
    ? t("offerCountdownExpired")
    : countdown.days >= 1
      ? t("offerCountdownDays", {
          days: countdown.days,
          hours: countdown.hours,
        })
      : countdown.hours >= 1
        ? t("offerCountdownHours", {
            hours: countdown.hours,
            minutes: countdown.minutes,
          })
        : t("offerCountdownMinutes", { minutes: countdown.minutes });

  return (
    <section className="mb-6 rounded-2xl border border-[var(--teal-400)]/30 bg-gradient-to-br from-[var(--teal-50)]/60 to-[var(--glass-surface)] p-4 shadow-[var(--shadow-md)] backdrop-blur-xl">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="inline-flex items-center gap-2 text-base font-bold text-[var(--text-primary)]">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-lg icon-chip-success shadow-sm">
            <Handshake
              aria-hidden
              weight="duotone"
              className="size-4 text-white"
            />
          </span>
          {t("offerTitle")}
        </h2>
        <StatusBadge tone={OFFER_STATUS_TONE[offer.status] ?? "info"}>
          {labels.status(offer.status, offer.status_label)}
        </StatusBadge>
      </div>

      <dl className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Meta label={t("offerPosition")}>
          {offer.position_title}
          {offer.department ? ` · ${offer.department}` : ""}
        </Meta>
        <Meta label={t("offerCompany")}>{jobTitle ?? t("untitledJob")}</Meta>
        <Meta label={t("offerComp")}>
          {offer.comp_summary ?? (
            <span className="text-[var(--text-secondary)]">
              {t("offerCompNotSet")}
            </span>
          )}
        </Meta>
        <Meta label={t("offerStartDate")}>
          {offer.start_date
            ? formatDateTime(offer.start_date, locale)
            : t("offerStartDateTbd")}
        </Meta>
      </dl>

      {/* Response deadline + live countdown (polite aria so it isn't noisy). */}
      <div className="mt-3 rounded-xl bg-[var(--glass-surface)] px-3.5 py-2.5">
        <p className="text-xs font-medium text-[var(--text-muted)]">
          {t("offerDeadline")}
        </p>
        <p className="mt-0.5 text-sm font-semibold text-[var(--text-primary)]">
          {formatDateTime(offer.expiry_date, locale)}
        </p>
        {isSent && (
          <p
            aria-live="polite"
            className={
              countdown.expired
                ? "mt-1 text-xs font-semibold text-[var(--brand-red)]"
                : "mt-1 text-xs font-medium text-[var(--amber-700)]"
            }
          >
            {countdownLabel}
          </p>
        )}
      </div>

      {/* Outcome / action region. */}
      {actionable ? (
        <div className="mt-4 flex flex-wrap gap-2">
          <Button
            variant="primary"
            onClick={() => setConfirm("accepted")}
            disabled={respond.isPending}
          >
            <SealCheck aria-hidden weight="bold" className="size-4" />
            {t("offerAccept")}
          </Button>
          <Button
            variant="secondary"
            onClick={() => {
              setDeclineNote("");
              setConfirm("declined");
            }}
            disabled={respond.isPending}
          >
            {t("offerDecline")}
          </Button>
        </div>
      ) : isSent && countdown.expired ? (
        <p className="mt-3 flex items-center gap-2 text-sm text-[var(--text-muted)]">
          <ShieldWarning aria-hidden weight="duotone" className="size-4" />
          {t("offerExpiredNote")}
        </p>
      ) : offer.status === "accepted" ? (
        <p className="mt-3 flex items-center gap-2 text-sm font-semibold text-[var(--teal-600)]">
          <SealCheck aria-hidden weight="duotone" className="size-4" />
          {t("offerAcceptedNote")}
        </p>
      ) : offer.status === "declined" ? (
        <p className="mt-3 flex items-center gap-2 text-sm text-[var(--text-muted)]">
          <ShieldWarning aria-hidden weight="duotone" className="size-4" />
          {t("offerDeclinedNote")}
        </p>
      ) : offer.status === "expired" ? (
        <p className="mt-3 flex items-center gap-2 text-sm text-[var(--text-muted)]">
          <ShieldWarning aria-hidden weight="duotone" className="size-4" />
          {t("offerExpiredNote")}
        </p>
      ) : offer.status === "rescinded" ? (
        <p className="mt-3 flex items-center gap-2 text-sm text-[var(--text-muted)]">
          <ShieldWarning aria-hidden weight="duotone" className="size-4" />
          {t("offerRescindedNote")}
        </p>
      ) : null}

      {/* Double-confirm modal — a significant decision, so it shows the offer
          summary and asks again. No confirm()/alert(). */}
      <Modal
        open={!!confirm}
        onClose={respond.isPending ? () => {} : () => setConfirm(null)}
        title={
          confirm === "accepted"
            ? t("offerAcceptConfirmTitle")
            : t("offerDeclineConfirmTitle")
        }
        description={
          confirm === "accepted"
            ? t("offerAcceptConfirmBody")
            : t("offerDeclineConfirmBody")
        }
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => setConfirm(null)}
              disabled={respond.isPending}
            >
              {tc("cancel")}
            </Button>
            <Button
              variant={confirm === "accepted" ? "primary" : "danger"}
              loading={respond.isPending}
              onClick={() => confirm && respond.mutate(confirm)}
            >
              {confirm === "accepted"
                ? t("offerAcceptConfirm")
                : t("offerDeclineConfirm")}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <dl className="rounded-xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-3 text-sm backdrop-blur-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-[var(--text-muted)]">{t("offerPosition")}</dt>
              <dd className="font-semibold text-[var(--text-primary)]">
                {offer.position_title}
              </dd>
            </div>
            {offer.comp_summary && (
              <div className="mt-1.5 flex justify-between gap-3">
                <dt className="text-[var(--text-muted)]">{t("offerComp")}</dt>
                <dd className="font-semibold text-[var(--text-primary)]">
                  {offer.comp_summary}
                </dd>
              </div>
            )}
            {offer.start_date && (
              <div className="mt-1.5 flex justify-between gap-3">
                <dt className="text-[var(--text-muted)]">
                  {t("offerStartDate")}
                </dt>
                <dd className="font-semibold text-[var(--text-primary)]">
                  {formatDateTime(offer.start_date, locale)}
                </dd>
              </div>
            )}
          </dl>
          {confirm === "accepted" ? (
            <p className="text-sm text-[var(--text-secondary)]">
              {t("offerAcceptIrreversible")}
            </p>
          ) : (
            <Textarea
              label={t("offerDeclineNoteLabel")}
              rows={3}
              maxLength={2000}
              value={declineNote}
              placeholder={t("offerDeclineNotePlaceholder")}
              help={t("offerDeclineNoteHelp")}
              onChange={(e) => setDeclineNote(e.target.value)}
            />
          )}
        </div>
      </Modal>
    </section>
  );
}
