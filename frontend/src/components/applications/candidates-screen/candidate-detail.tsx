"use client";

import { useTranslations } from "next-intl";
import { Download, FileText, ShieldAlert, Sparkles } from "lucide-react";
import { Button } from "@/components/ui";
import { EmptyState } from "@/components/kit";
import { useRejectionReasonLabel } from "@/lib/applications/labels";
import { resolveDownloadUrl, type PartnerApplication } from "@/lib/api";

/**
 * Candidate detail BODY — the drawer's hero content is the CANDIDATE'S CV,
 * rendered inline (watermarked PDF) so a recruiter can review the résumé the way
 * they would in a modern ATS. Identity, the match ring, prev/next, and the
 * review/reject decision live in the sheet header + footer; this body stays
 * deliberately focused on the document (no scorecard / screening / offer forms).
 * A slim fit-evidence strip and the rejection outcome are read-only context.
 */
export function CandidateDetail({
  app,
  downloading,
  onDownload,
}: {
  app: PartnerApplication;
  downloading: boolean;
  onDownload: () => void;
}) {
  const t = useTranslations("candidates");
  const reasonLabel = useRejectionReasonLabel();
  const cv = app.cv ?? null;
  const fit = app.fit ?? null;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Rejection outcome (partner-only reason + note) — read-only context. */}
      {app.status === "rejected" && app.rejection_reason && (
        <div className="shrink-0 border-b border-border px-4 py-3">
          <div className="rounded-lg p-3" style={{ background: "var(--content-danger-soft)" }}>
            <p
              className="text-[0.8125rem] font-semibold"
              style={{ color: "var(--content-danger)" }}
            >
              {reasonLabel(app.rejection_reason)}
            </p>
            {app.rejection_note && (
              <p className="mt-1.5 whitespace-pre-wrap type-small text-muted-foreground">
                {app.rejection_note}
              </p>
            )}
          </div>
          <p className="mt-1.5 type-caption text-muted-foreground">{t("partnerOnlyNote")}</p>
        </div>
      )}

      {/* Fit evidence — short, privacy-safe reasons behind the match score. */}
      {fit && fit.reasons.length > 0 && (
        <div className="shrink-0 border-b border-border px-4 py-3">
          <p className="mb-1.5 flex items-center gap-1.5 text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
            <Sparkles aria-hidden className="size-3.5" strokeWidth={1.9} />
            {t("fitReasonsTitle")}
          </p>
          <ul className="space-y-1">
            {fit.reasons.slice(0, 5).map((reason, i) => (
              <li key={i} className="flex items-start gap-1.5 type-small text-foreground">
                <span
                  aria-hidden
                  className="mt-[0.4rem] size-1 shrink-0 rounded-full bg-[var(--text-muted)]"
                />
                <span>{reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* CV viewer — inline watermarked PDF fills the drawer. */}
      {cv ? (
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border px-4 py-2.5">
            <span className="inline-flex min-w-0 items-center gap-1.5 type-small font-medium text-foreground">
              <FileText aria-hidden className="size-4 shrink-0 text-muted-foreground" strokeWidth={1.8} />
              <span className="truncate">{cv.filename || t("cvFilenameFallback")}</span>
            </span>
            <Button variant="secondary" size="sm" loading={downloading} onClick={onDownload}>
              <Download aria-hidden className="size-4" strokeWidth={1.8} />
              {t("downloadCv")}
            </Button>
          </div>
          <iframe
            title={t("cvViewerTitle")}
            src={resolveDownloadUrl(cv.view_url)}
            className="min-h-[60vh] w-full flex-1 border-0 bg-[var(--bg-muted)]"
          />
          <p className="flex shrink-0 items-start gap-1.5 border-t border-border px-4 py-2 type-caption text-muted-foreground">
            <ShieldAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" strokeWidth={1.8} />
            {t("watermarkNote")}
          </p>
        </div>
      ) : (
        <div className="flex min-h-[50vh] flex-1 items-center justify-center p-5">
          <EmptyState
            kind="empty"
            icon={FileText}
            title={t("cvNotReadyTitle")}
            description={t("cvNotReadyBody")}
          />
        </div>
      )}
    </div>
  );
}
