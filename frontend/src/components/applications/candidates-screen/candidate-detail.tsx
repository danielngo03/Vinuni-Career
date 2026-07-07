"use client";

import { useTranslations } from "next-intl";
import {
  DownloadSimple,
  MagnifyingGlass,
  Prohibit,
  ShieldWarning,
  UserFocus,
  WarningCircle,
} from "@phosphor-icons/react";
import { Button, StatusBadge } from "@/components/ui";
import {
  APPLICATION_STATUS_TONE,
  REVEAL_STATUS_TONE,
  useApplicationLabels,
  useRejectionReasonLabel,
} from "@/lib/applications/labels";
import type { ApplicantRankingItem, PartnerApplication } from "@/lib/api";
import { PartnerScorecardPanel } from "../partner-scorecard-panel";
import { PartnerInterviewPanel } from "../partner-interview-panel";
import { PartnerOfferPanel } from "../partner-offer-panel";
import { MessageCandidateButton } from "@/components/messaging/message-candidate-button";
import { AiScreeningBrief } from "../ai-screening-brief";
import { FitChip } from "./fit-chip";
import { CvPreviewPane } from "./cv-preview-pane";

export function CandidateDetail({
  app,
  jobTitle,
  fit,
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
  /** Assistive CV↔JD fit for this candidate, when the ranking read model has it. */
  fit?: ApplicantRankingItem | null;
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
  const displayName = anonUnrevealed
    ? app.applicant.anonymous_id ?? app.applicant.display_name
    : app.applicant.display_name;

  return (
    <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:items-start lg:gap-6">
      {/* LEFT: identity, fit, decisions, brief, cover letter, evaluation panels */}
      <div className="space-y-5">
        {/* Identity */}
        <div>
          <p className="text-base font-bold text-[var(--text-primary)]">
            {displayName}
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

        {/* Assistive CV↔JD fit — advisory only, never an automated decision */}
        {fit && (
          <section className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-subtle)]/40 p-3.5">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-sm font-bold text-[var(--text-primary)]">
                {t("fitTitle")}
              </h3>
              <FitChip score={fit.fit_score} band={fit.fit_band} size="md" />
            </div>
            <p className="mt-1 text-[11px] text-[var(--text-muted)]">
              {t("fitAdvisory")}
            </p>
            {fit.stale && (
              <p className="mt-2 flex items-center gap-1.5 text-[11px] font-medium text-[var(--amber-700)]">
                <WarningCircle
                  aria-hidden
                  weight="duotone"
                  className="size-3.5 shrink-0"
                />
                {t("fitStale")}
              </p>
            )}
            {(fit.matched_skills.length > 0 || fit.gaps.length > 0) && (
              <div className="mt-3 space-y-2">
                {fit.matched_skills.length > 0 && (
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                      {t("fitMatchedLabel")}
                    </p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {fit.matched_skills.map((s) => (
                        <span
                          key={s}
                          className="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700"
                        >
                          {s}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {fit.gaps.length > 0 && (
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                      {t("fitGapsLabel")}
                    </p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {fit.gaps.map((s) => (
                        <span
                          key={s}
                          className="inline-flex items-center rounded-full border border-[var(--border-default)] bg-[var(--bg-subtle)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]"
                        >
                          {s}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </section>
        )}

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

      {/* RIGHT: embedded, watermarked CV preview pinned beside the review panel.
          On mobile it stacks below the review content as a preview + open link. */}
      <div className="mt-6 lg:sticky lg:top-0 lg:mt-0 lg:h-[calc(100vh-9.5rem)]">
        <CvPreviewPane
          applicationId={app.id}
          available={app.cv_download_available}
          displayName={displayName}
        />
      </div>
    </div>
  );
}
