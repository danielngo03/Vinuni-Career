"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import {
  AlertCircle,
  ArrowRight,
  CheckSquare,
  Clock,
  Download,
  ExternalLink,
  Handshake,
  History,
  Square,
  Undo2,
  UserRound,
} from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Button, useToast } from "@/components/ui";
import { KanbanCard, StatusChip, type ChipTone } from "@/components/kit";
import { formatDateTime } from "@/lib/format";
import { useOfferLabels } from "@/lib/applications/labels";
import { applicationsApi, resolveDownloadUrl, type PipelineCard } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { cardHandle, daysInStage, OFFER_CHIP_TONE, STALE_DAYS } from "./utils";

export function PipelineCardView({
  card,
  columnId,
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
  /** Droppable column id this card belongs to (stage_id ?? "__new__"). */
  columnId: string;
  isNewBucket: boolean;
  canAdvance: boolean;
  jobId: string;
  requiredAction: string | null;
  canRollback: boolean;
  locale: string;
  statusTone: (status: string) => ChipTone;
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

  const evalGated = requiredAction === "scorecard" || requiredAction === "score_threshold";
  const ev = card.evaluation ?? null;
  const showGate = evalGated && ev != null && ev.required > 0;
  const gateBlocked = showGate && ev!.gate_met === false;

  // A card is draggable when it has somewhere to go (forward or backward).
  const draggable = canAdvance || canRollback;

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
    <KanbanCard
      id={card.application_id}
      columnId={columnId}
      disabled={!draggable}
      selected={isSelected}
      dragLabel={t("dragCardAria", { handle })}
    >
      {/* Header: select toggle + external link + rollback badge */}
      <div className="flex items-start justify-between gap-2">
        <button
          type="button"
          aria-label={isSelected ? t("deselectCard") : t("selectCard")}
          aria-pressed={isSelected}
          onClick={onToggleSelect}
          className="inline-flex min-w-0 items-center gap-1.5 rounded text-[0.8125rem] font-semibold text-foreground outline-none focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
        >
          {isSelected ? (
            <CheckSquare aria-hidden className="size-4 shrink-0 text-[var(--brand-primary)]" strokeWidth={2} />
          ) : anon ? (
            <UserRound aria-hidden className="size-4 shrink-0 text-muted-foreground" strokeWidth={1.8} />
          ) : (
            <Square aria-hidden className="size-4 shrink-0 text-muted-foreground" strokeWidth={1.8} />
          )}
          <span className="truncate">{handle}</span>
        </button>
        <div className="flex shrink-0 items-center gap-1">
          <Link
            href={`/partner/jobs/${jobId}/applications?selected=${card.application_id}`}
            className="inline-flex items-center rounded p-0.5 text-muted-foreground outline-none hover:text-[var(--brand-primary)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
            title={t("viewCandidate")}
            aria-label={t("viewCandidate")}
          >
            <ExternalLink aria-hidden className="size-3.5" strokeWidth={1.8} />
          </Link>
          {card.rollback_count > 0 && (
            <StatusChip tone="amber" size="sm" title={t("rollbackBadgeTitle", { count: card.rollback_count })}>
              <History aria-hidden className="size-3" strokeWidth={2} />
              {card.rollback_count}
            </StatusChip>
          )}
        </div>
      </div>

      {/* Status + position */}
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <StatusChip tone={statusTone(card.status)} size="sm">
          {statusLabel(card.status, card.status_label)}
        </StatusChip>
        {card.position != null && (
          <span className="type-caption text-muted-foreground">{t("positionLabel", { n: card.position })}</span>
        )}
      </div>

      {/* SLA aging / applied date */}
      {days !== null && card.entered_at ? (
        <p
          className={
            stale
              ? "mt-2 inline-flex items-center gap-1 text-[0.6875rem] font-medium text-[var(--content-warning)]"
              : "mt-2 inline-flex items-center gap-1 text-[0.6875rem] text-muted-foreground"
          }
        >
          <Clock aria-hidden className="size-3" strokeWidth={1.9} />
          {days <= 0 ? t("enteredToday") : t("inStageDays", { count: days })}
          {" · "}
          {formatDateTime(card.entered_at, locale)}
        </p>
      ) : (
        <p className="mt-2 type-caption text-muted-foreground">
          {t("appliedAt", { date: formatDateTime(card.applied_at, locale) })}
        </p>
      )}

      {/* Evaluation gate */}
      {showGate && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="type-caption font-medium text-muted-foreground">
            {t("gateScorecards", { submitted: ev!.submitted_count, required: ev!.required })}
          </span>
          {ev!.avg_overall != null && (
            <span className="type-caption font-medium text-muted-foreground">
              {t("gateAvg", { avg: ev!.avg_overall.toFixed(1) })}
            </span>
          )}
          {gateBlocked && (
            <StatusChip tone="warning" size="sm" title={t("scorecardRequiredHint")}>
              <AlertCircle aria-hidden className="size-3" strokeWidth={1.9} />
              {requiredAction === "score_threshold" ? t("scoreGateBlocked") : t("scorecardRequired")}
            </StatusChip>
          )}
        </div>
      )}

      {/* Offer glance (status + deadline only — never salary on the board) */}
      {card.offer && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <StatusChip tone={OFFER_CHIP_TONE[card.offer.status] ?? "neutral"} size="sm">
            <Handshake aria-hidden className="size-3" strokeWidth={1.9} />
            {offerLabels.status(card.offer.status, card.offer.status_label)}
          </StatusChip>
          {card.offer.expiry_date && (
            <span className="type-caption text-muted-foreground">
              {t("offerExpires", { date: formatDateTime(card.offer.expiry_date, locale) })}
            </span>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        {canAdvance && (
          <Button variant="primary" size="sm" loading={advancePending} onClick={onAdvance}>
            <ArrowRight aria-hidden className="size-4" strokeWidth={2} />
            {isNewBucket ? t("startStage") : t("advance")}
          </Button>
        )}
        {canRollback && (
          <Button variant="ghost" size="sm" onClick={onRollback}>
            <Undo2 aria-hidden className="size-4" strokeWidth={2} />
            {t("rollback")}
          </Button>
        )}
        {card.cv_download_available && (
          <Button variant="ghost" size="sm" loading={downloading} onClick={handleDownload}>
            <Download aria-hidden className="size-4" strokeWidth={1.8} />
            {t("cv")}
          </Button>
        )}
      </div>
    </KanbanCard>
  );
}
