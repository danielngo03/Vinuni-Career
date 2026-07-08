"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import {
  ArrowRight,
  ArrowSquareOut,
  ArrowUDownLeft,
  CheckSquare,
  ClockCounterClockwise,
  DownloadSimple,
  Handshake,
  Square,
  UserFocus,
  WarningCircle,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, StatusBadge, useToast } from "@/components/ui";
import { formatDateTime } from "@/lib/format";
import { OFFER_STATUS_TONE, useOfferLabels } from "@/lib/applications/labels";
import { applicationsApi, resolveDownloadUrl, type PipelineCard } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { cardHandle, daysInStage, STALE_DAYS } from "./utils";

export function PipelineCardView({
  card,
  isNewBucket,
  canAdvance,
  jobId,
  requiredAction,
  canRollback,
  locale,
  statusTone,
  statusLabel,
  advancePending,
  isSelected,
  onToggleSelect,
  onAdvance,
  onRollback,
  t,
}: {
  card: PipelineCard;
  isNewBucket: boolean;
  canAdvance: boolean;
  jobId: string;
  requiredAction: string | null;
  canRollback: boolean;
  locale: string;
  statusTone: (status: string) => Parameters<typeof StatusBadge>[0]["tone"];
  statusLabel: (status: string, label?: string | null) => string;
  advancePending: boolean;
  isSelected: boolean;
  onToggleSelect: () => void;
  onAdvance: () => void;
  onRollback: () => void;
  t: ReturnType<typeof useTranslations>;
}) {
  const toast = useToast();
  const apiError = useApiErrorMessage();
  const offerLabels = useOfferLabels();
  const [downloading, setDownloading] = useState(false);
  const handle = cardHandle(card);
  const anon = card.is_anonymous && !card.applicant.display_name;
  const days = daysInStage(card.entered_at);
  const stale = days !== null && days >= STALE_DAYS;
  // `scorecard` / `score_threshold` stages block advance until the gate is met;
  // the server enforces it (409), but we surface the gate state up front on the
  // card. `score_threshold` also requires the average score to reach the
  // threshold (the board glance shows counts + avg; the precise 409 is a toast).
  const evalGated =
    requiredAction === "scorecard" || requiredAction === "score_threshold";
  const ev = card.evaluation ?? null;
  const showGate = evalGated && ev != null && ev.required > 0;
  const gateBlocked = showGate && ev!.gate_met === false;

  async function handleDownload() {
    setDownloading(true);
    try {
      const info = await applicationsApi.getCvDownload(card.application_id);
      window.open(resolveDownloadUrl(info.download_url), "_blank", "noopener");
      toast.show({ tone: "success", title: t("downloadStarted") });
    } catch (e) {
      toast.show({ tone: "error", title: apiError(e) });
    } finally {
      setDownloading(false);
    }
  }

  return (
    <article
      className={`rounded-xl border p-3 shadow-[0_1px_8px_rgba(11,34,57,0.06)] transition-colors ${
        isSelected
          ? "border-[var(--brand-primary)]/60 bg-[var(--brand-primary)]/8"
          : "border-[var(--border-default)] bg-white"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          aria-label={isSelected ? t("deselectCard") : t("selectCard")}
          aria-pressed={isSelected}
          onClick={onToggleSelect}
          className="inline-flex min-w-0 items-center gap-1.5 text-sm font-semibold text-[var(--text-primary)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30 rounded"
        >
          {isSelected ? (
            <CheckSquare
              aria-hidden
              weight="fill"
              className="size-4 shrink-0 text-[var(--brand-primary)]"
            />
          ) : anon ? (
            <UserFocus
              aria-hidden
              weight="duotone"
              className="size-4 shrink-0 text-[var(--text-muted)]"
            />
          ) : (
            <Square
              aria-hidden
              weight="regular"
              className="size-4 shrink-0 text-[var(--text-muted)]"
            />
          )}
          <span className="truncate">{handle}</span>
        </button>
        <div className="flex shrink-0 items-center gap-1">
          <Link
            href={`/partner/jobs/${jobId}/applications?selected=${card.application_id}`}
            className="inline-flex items-center rounded p-0.5 text-[var(--text-muted)] outline-none hover:text-[var(--brand-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
            title={t("viewCandidate")}
            aria-label={t("viewCandidate")}
          >
            <ArrowSquareOut aria-hidden weight="bold" className="size-3.5" />
          </Link>
          {card.rollback_count > 0 && (
            <span
              className="inline-flex shrink-0 items-center gap-1 rounded-full bg-[var(--amber-100)] px-2 py-0.5 text-[11px] font-semibold text-[var(--amber-700)]"
              title={t("rollbackBadgeTitle", { count: card.rollback_count })}
            >
              <ClockCounterClockwise aria-hidden weight="bold" className="size-3" />
              {card.rollback_count}
            </span>
          )}
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <StatusBadge tone={statusTone(card.status)}>
          {statusLabel(card.status, card.status_label)}
        </StatusBadge>
        {card.position != null && (
          <span className="text-[11px] text-[var(--text-muted)]">
            {t("positionLabel", { n: card.position })}
          </span>
        )}
      </div>

      {/* Stage freshness only applies once a card has a stage row; the "new"
          pre-pipeline bucket has a null entered_at, so show the applied date. */}
      {days !== null && card.entered_at ? (
        <p
          className={
            stale
              ? "mt-2 text-[11px] font-medium text-[var(--amber-700)]"
              : "mt-2 text-[11px] text-[var(--text-muted)]"
          }
        >
          {days <= 0 ? t("enteredToday") : t("inStageDays", { count: days })}
          {" · "}
          {formatDateTime(card.entered_at, locale)}
        </p>
      ) : (
        <p className="mt-2 text-[11px] text-[var(--text-muted)]">
          {t("appliedAt", { date: formatDateTime(card.applied_at, locale) })}
        </p>
      )}

      {/* Extended gate state (ADR-0006): submitted/required scorecards + average
          when present, plus the advance-blocked badge. */}
      {showGate && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] font-medium text-[var(--text-secondary)]">
            {t("gateScorecards", {
              submitted: ev!.submitted_count,
              required: ev!.required,
            })}
          </span>
          {ev!.avg_overall != null && (
            <span className="text-[11px] font-medium text-[var(--text-secondary)]">
              {t("gateAvg", { avg: ev!.avg_overall.toFixed(1) })}
            </span>
          )}
          {gateBlocked && (
            <span
              role="status"
              className="inline-flex items-center gap-1 rounded-full bg-[var(--amber-100)] px-2 py-0.5 text-[11px] font-semibold text-[var(--amber-700)]"
              title={t("scorecardRequiredHint")}
            >
              <WarningCircle aria-hidden weight="duotone" className="size-3" />
              {requiredAction === "score_threshold"
                ? t("scoreGateBlocked")
                : t("scorecardRequired")}
            </span>
          )}
        </div>
      )}

      {/* Offer glance (ADR-0007 §8): status + deadline ONLY — NO salary on the
          board (open the candidate detail to see comp). Rendered only when the
          card's current stage carries an offer. */}
      {card.offer && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <StatusBadge tone={OFFER_STATUS_TONE[card.offer.status] ?? "info"}>
            <Handshake aria-hidden weight="duotone" className="size-3" />
            {offerLabels.status(card.offer.status, card.offer.status_label)}
          </StatusBadge>
          {card.offer.expiry_date && (
            <span className="text-[11px] text-[var(--text-muted)]">
              {t("offerExpires", {
                date: formatDateTime(card.offer.expiry_date, locale),
              })}
            </span>
          )}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        {canAdvance && (
          <Button
            variant="primary"
            size="sm"
            loading={advancePending}
            onClick={onAdvance}
          >
            <ArrowRight aria-hidden weight="bold" className="size-4" />
            {isNewBucket ? t("startStage") : t("advance")}
          </Button>
        )}
        {canRollback && (
          <Button variant="ghost" size="sm" onClick={onRollback}>
            <ArrowUDownLeft aria-hidden weight="bold" className="size-4" />
            {t("rollback")}
          </Button>
        )}
        {card.cv_download_available && (
          <Button
            variant="ghost"
            size="sm"
            loading={downloading}
            onClick={handleDownload}
          >
            <DownloadSimple aria-hidden weight="duotone" className="size-4" />
            {t("cv")}
          </Button>
        )}
      </div>
    </article>
  );
}
