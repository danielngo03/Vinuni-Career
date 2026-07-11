"use client";

import { useTranslations } from "next-intl";
import { Modal } from "@/components/ui";
import { PartnerScorecardPanel } from "../partner-scorecard-panel";

/**
 * Focused scorecard surface opened from a pipeline-board card (the P0 re-home of
 * the scorecard workflow — the CV-first candidate drawer stays CV-only).
 *
 * The stage/gate context lives on the board, so this is where a recruiter scores
 * a candidate sitting in a `scorecard` / `score_threshold`-gated stage. The
 * modal only provides the title + who/which-stage context; the embedded
 * `PartnerScorecardPanel` (rendered with `hideHeader`) owns the real workflow:
 * the criteria form, recommendation, submit/edit/withdraw, anchoring, and the
 * stage aggregate. On submit the panel invalidates the `["applications",
 * "pipeline"]` query, so the board's advance gate refreshes honestly.
 *
 * Rendered ONLY while a target is set (the parent gates on it), so the panel's
 * scorecard read fires exactly when the modal is open — never in the background.
 */
export function ScorecardModal({
  applicationId,
  handle,
  stageName,
  canSubmit,
  jobTitle,
  onClose,
}: {
  applicationId: string;
  /** Candidate display name — for the modal's context line. */
  handle: string;
  /** Current pipeline stage name — for the modal's context line. */
  stageName: string;
  /**
   * Whether the caller may submit/edit a scorecard (holds `scorecards:submit`
   * AND the candidate is under review). When false the panel is read-only — the
   * server remains the final authority.
   */
  canSubmit: boolean;
  jobTitle?: string;
  onClose: () => void;
}) {
  const t = useTranslations("pipeline");
  const tc = useTranslations("common");

  return (
    <Modal
      open
      onClose={onClose}
      title={t("scorecardModalTitle")}
      description={t("scorecardModalContext", { handle, stage: stageName })}
      size="lg"
      closeLabel={tc("close")}
    >
      <PartnerScorecardPanel
        applicationId={applicationId}
        canSubmit={canSubmit}
        jobTitle={jobTitle}
        hideHeader
      />
    </Modal>
  );
}
