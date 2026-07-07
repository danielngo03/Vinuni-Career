"use client";

import { useTranslations } from "next-intl";
import {
  DownloadSimple,
  MagnifyingGlass,
  Prohibit,
  ShieldWarning,
  UserFocus,
} from "@phosphor-icons/react";
import { Button, StatusBadge } from "@/components/ui";
import {
  APPLICATION_STATUS_TONE,
  REVEAL_STATUS_TONE,
  useApplicationLabels,
  useRejectionReasonLabel,
} from "@/lib/applications/labels";
import type { PartnerApplication } from "@/lib/api";
import { PartnerScorecardPanel } from "../partner-scorecard-panel";
import { PartnerInterviewPanel } from "../partner-interview-panel";
import { PartnerOfferPanel } from "../partner-offer-panel";
import { MessageCandidateButton } from "@/components/messaging/message-candidate-button";
import { AiScreeningBrief } from "../ai-screening-brief";

export function CandidateDetail({
  app,
  jobTitle,
  downloading,
  reviewPending,
  rejectPending,
  onDownload,
  onOpenReveal,
  onStartReview,
  onOpenReject,
}: {
  app: PartnerApplication;
  jobTitle?: string;
  downloading: boolean;
  reviewPending: boolean;
  rejectPending: boolean;
  onDownload: () => void;
  onOpenReveal: () => void;
  onStartReview: () => void;
  onOpenReject: () => void;
}) {
  const t = useTranslations("candidates");
  const labels = useApplicationLabels();
  const reasonLabel = useRejectionReasonLabel();
  const anonUnrevealed = app.applicant.is_anonymous && !app.applicant.revealed;
  const canReview = app.status === "submitted";
  const canReject = app.status === "submitted" || app.status === "under_review";

  return (
    <div className="space-y-5">
      {/* Identity */}
      <div>
        <p className="text-base font-bold text-[var(--text-primary)]">
          {anonUnrevealed
            ? app.applicant.anonymous_id ?? app.applicant.display_name
            : app.applicant.display_name}
        </p>
        {!anonUnrevealed && app.applicant.email && (
          <p className="text-sm text-[var(--text-secondary)]">
            {app.applicant.email}
          </p>
        )}
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <StatusBadge tone={APPLICATION_STATUS_TONE[app.status] ?? "info"}>
            {labels.status(app.status, app.status_label)}
          </StatusBadge>
          {app.applicant.is_anonymous && (
            <StatusBadge tone={REVEAL_STATUS_TONE[app.reveal_status] ?? "draft"}>
              {labels.reveal(app.reveal_status, app.reveal_status_label)}
            </StatusBadge>
          )}
        </div>
        <div className="mt-3">
          <MessageCandidateButton applicationId={app.id} />
        </div>
      </div>

      {/* Decision actions */}
      {(canReview || canReject) && (
        <div className="flex flex-wrap gap-2 border-y border-[var(--border-subtle)] py-4">
          {canReview && (
            <Button
              variant="primary"
              size="sm"
              loading={reviewPending}
              disabled={rejectPending}
              onClick={onStartReview}
            >
              <MagnifyingGlass aria-hidden weight="bold" className="size-4" />
              {t("startReview")}
            </Button>
          )}
          {canReject && (
            <Button
              variant="danger"
              size="sm"
              disabled={reviewPending || rejectPending}
              onClick={onOpenReject}
            >
              <Prohibit aria-hidden weight="bold" className="size-4" />
              {t("reject")}
            </Button>
          )}
        </div>
      )}

      {/* Rejection outcome (partner-only reason + note) */}
      {app.status === "rejected" && app.rejection_reason && (
        <section className="rounded-xl border border-[var(--red-400)]/40 bg-[var(--red-50)] p-3.5">
          <h3 className="text-sm font-bold text-[var(--brand-red)]">
            {t("rejectionLabel")}
          </h3>
          <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">
            {reasonLabel(app.rejection_reason)}
          </p>
          {app.rejection_note && (
            <>
              <p className="mt-3 text-xs font-medium text-[var(--text-muted)]">
                {t("rejectionNoteLabel")}
              </p>
              <p className="mt-0.5 whitespace-pre-wrap text-sm text-[var(--text-secondary)]">
                {app.rejection_note}
              </p>
            </>
          )}
          <p className="mt-2 text-xs text-[var(--text-muted)]">
            {t("partnerOnlyNote")}
          </p>
        </section>
      )}

      {anonUnrevealed && (
        <div className="rounded-xl border border-white/60 bg-white/72 p-3.5 backdrop-blur-sm">
          <p className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
            <span className="flex size-5 shrink-0 items-center justify-center rounded-md icon-chip-warning shadow-sm">
              <ShieldWarning aria-hidden weight="duotone" className="size-3 text-white" />
            </span>
            {t("anonymousNotice")}
          </p>
        </div>
      )}

      {/* AI Screening Brief */}
      <div>
        <AiScreeningBrief applicationId={app.id} />
      </div>

      {/* Cover letter */}
      {app.cover_letter ? (
        <section>
          <h3 className="mb-1.5 text-sm font-bold text-[var(--text-primary)]">
            {t("coverLetter")}
          </h3>
          <p className="whitespace-pre-wrap rounded-xl border border-white/60 bg-white/82 backdrop-blur-md p-3 text-sm leading-relaxed text-[var(--text-secondary)]">
            {app.cover_letter}
          </p>
        </section>
      ) : anonUnrevealed ? (
        <p className="text-sm text-[var(--text-muted)]">{t("hiddenUntilReveal")}</p>
      ) : null}

      {/* Scorecard (partner-internal evaluation; never shown to the student). */}
      <div className="border-t border-white/40 pt-4">
        <PartnerScorecardPanel
          applicationId={app.id}
          canSubmit={app.status === "under_review"}
          jobTitle={jobTitle}
        />
      </div>

      {/* Interviews (partner-internal scheduling; ADR-0006). The student sees only
          their own upcoming-interview card on the student application detail. */}
      <div className="border-t border-white/40 pt-4">
        <PartnerInterviewPanel
          applicationId={app.id}
          canSchedule={app.status === "under_review"}
          anonUnrevealed={anonUnrevealed}
          revealPending={app.reveal_status === "pending"}
          onRequestReveal={onOpenReveal}
        />
      </div>

      {/* Offers (ADR-0007). Partner-internal create→approve→send flow; the comp is
          recruiter-visible here but NEVER on the board glance. The student sees only
          their own offer card on the student application detail. */}
      <div className="border-t border-white/40 pt-4">
        <PartnerOfferPanel
          applicationId={app.id}
          canCreate={app.status === "under_review"}
          anonUnrevealed={anonUnrevealed}
          revealPending={app.reveal_status === "pending"}
          onRequestReveal={onOpenReveal}
        />
      </div>

      {/* Actions */}
      <div className="flex flex-col gap-2 border-t border-white/40 pt-4">
        <Button
          variant="primary"
          fullWidth
          loading={downloading}
          disabled={!app.cv_download_available}
          onClick={onDownload}
        >
          <DownloadSimple aria-hidden weight="bold" className="size-4" />
          {t("downloadCv")}
        </Button>
        {!app.cv_download_available && (
          <p className="text-xs text-[var(--text-muted)]">
            {t("downloadBlocked")}
          </p>
        )}
        <p className="flex items-start gap-1.5 text-xs text-[var(--text-muted)]">
          <ShieldWarning aria-hidden weight="duotone" className="mt-0.5 size-3.5 shrink-0" />
          {t("watermarkNote")}
        </p>

        {anonUnrevealed && app.reveal_status !== "pending" && (
          <Button variant="secondary" fullWidth onClick={onOpenReveal}>
            <UserFocus aria-hidden weight="bold" className="size-4" />
            {t("requestReveal")}
          </Button>
        )}
        {anonUnrevealed && app.reveal_status === "pending" && (
          <p className="text-xs text-[var(--amber-700)]">
            {t("revealPending")}
          </p>
        )}
      </div>
    </div>
  );
}
