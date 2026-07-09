"use client";

import { useTranslations } from "next-intl";
import { Download, Eye, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui";
import { DetailSheetSection } from "@/components/kit";
import { useRejectionReasonLabel } from "@/lib/applications/labels";
import type { PartnerApplication } from "@/lib/api";
import { PartnerScorecardPanel } from "../partner-scorecard-panel";
import { PartnerInterviewPanel } from "../partner-interview-panel";
import { PartnerOfferPanel } from "../partner-offer-panel";
import { AiScreeningBrief } from "../ai-screening-brief";

/**
 * Candidate detail BODY — rendered inside the v10 {@link DetailSheet} on the
 * partner candidates screen. Identity/status/decision actions live in the sheet
 * header + footer; this composes the sectioned body: rejection outcome, AI
 * screening brief, cover letter, the partner-internal scorecard / interview /
 * offer panels, and the watermarked CV download + reveal-with-reason CTA.
 */
export function CandidateDetail({
  app,
  jobTitle,
  downloading,
  onDownload,
  onOpenReveal,
}: {
  app: PartnerApplication;
  jobTitle?: string;
  downloading: boolean;
  onDownload: () => void;
  onOpenReveal: () => void;
}) {
  const t = useTranslations("candidates");
  const reasonLabel = useRejectionReasonLabel();
  const anonUnrevealed = app.applicant.is_anonymous && !app.applicant.revealed;

  return (
    <div>
      {/* Rejection outcome (partner-only reason + note). */}
      {app.status === "rejected" && app.rejection_reason && (
        <DetailSheetSection title={t("rejectionLabel")}>
          <div
            className="rounded-lg p-3"
            style={{ background: "var(--content-danger-soft)" }}
          >
            <p className="text-[0.8125rem] font-semibold" style={{ color: "var(--content-danger)" }}>
              {reasonLabel(app.rejection_reason)}
            </p>
            {app.rejection_note && (
              <p className="mt-2 whitespace-pre-wrap type-small text-muted-foreground">
                {app.rejection_note}
              </p>
            )}
          </div>
          <p className="mt-2 type-caption text-muted-foreground">{t("partnerOnlyNote")}</p>
        </DetailSheetSection>
      )}

      {/* Anonymous privacy notice. */}
      {anonUnrevealed && (
        <DetailSheetSection>
          <div
            className="flex items-start gap-2.5 rounded-lg p-3"
            style={{ background: "var(--content-warning-soft)" }}
          >
            <ShieldAlert
              aria-hidden
              className="mt-0.5 size-4 shrink-0"
              strokeWidth={1.8}
              style={{ color: "var(--content-warning)" }}
            />
            <p className="type-small text-muted-foreground">{t("anonymousNotice")}</p>
          </div>
        </DetailSheetSection>
      )}

      {/* AI screening brief (advisory, masked). */}
      <DetailSheetSection>
        <AiScreeningBrief applicationId={app.id} />
      </DetailSheetSection>

      {/* Cover letter. */}
      {app.cover_letter ? (
        <DetailSheetSection title={t("coverLetter")}>
          <p className="whitespace-pre-wrap rounded-lg border border-border bg-[var(--bg-subtle)] p-3 type-small leading-relaxed text-foreground">
            {app.cover_letter}
          </p>
        </DetailSheetSection>
      ) : anonUnrevealed ? (
        <DetailSheetSection title={t("coverLetter")}>
          <p className="type-small text-muted-foreground">{t("hiddenUntilReveal")}</p>
        </DetailSheetSection>
      ) : null}

      {/* Scorecard (partner-internal; never shown to the student). */}
      <DetailSheetSection>
        <PartnerScorecardPanel
          applicationId={app.id}
          canSubmit={app.status === "under_review"}
          jobTitle={jobTitle}
        />
      </DetailSheetSection>

      {/* Interviews (partner-internal scheduling; ADR-0006). */}
      <DetailSheetSection>
        <PartnerInterviewPanel
          applicationId={app.id}
          canSchedule={app.status === "under_review"}
          anonUnrevealed={anonUnrevealed}
          revealPending={app.reveal_status === "pending"}
          onRequestReveal={onOpenReveal}
        />
      </DetailSheetSection>

      {/* Offers (ADR-0007). Comp is recruiter-visible here, never on board glance. */}
      <DetailSheetSection>
        <PartnerOfferPanel
          applicationId={app.id}
          canCreate={app.status === "under_review"}
          anonUnrevealed={anonUnrevealed}
          revealPending={app.reveal_status === "pending"}
          onRequestReveal={onOpenReveal}
        />
      </DetailSheetSection>

      {/* CV & documents. */}
      <DetailSheetSection title={t("cvSectionTitle")}>
        <Button
          variant="primary"
          fullWidth
          loading={downloading}
          disabled={!app.cv_download_available}
          onClick={onDownload}
        >
          <Download aria-hidden className="size-4" strokeWidth={1.8} />
          {t("downloadCv")}
        </Button>
        {!app.cv_download_available && (
          <p className="mt-2 type-caption text-muted-foreground">{t("downloadBlocked")}</p>
        )}
        <p className="mt-2 flex items-start gap-1.5 type-caption text-muted-foreground">
          <ShieldAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" strokeWidth={1.8} />
          {t("watermarkNote")}
        </p>

        {anonUnrevealed && app.reveal_status !== "pending" && (
          <Button variant="secondary" fullWidth className="mt-3" onClick={onOpenReveal}>
            <Eye aria-hidden className="size-4" strokeWidth={1.8} />
            {t("requestReveal")}
          </Button>
        )}
        {anonUnrevealed && app.reveal_status === "pending" && (
          <p className="mt-3 type-caption" style={{ color: "var(--content-warning)" }}>
            {t("revealPending")}
          </p>
        )}
      </DetailSheetSection>
    </div>
  );
}
