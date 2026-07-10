"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import {
  ClipboardList,
  Download,
  FileText,
  MessageSquareText,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui";
import { EmptyState } from "@/components/kit";
import { cn } from "@/lib/utils";
import { useRejectionReasonLabel } from "@/lib/applications/labels";
import { resolveDownloadUrl, type PartnerApplication } from "@/lib/api";
import { CvEvaluationPanel } from "./cv-evaluation-panel";
import { isOpaqueQuestionKey } from "./utils";

type DetailTab = "cv" | "application" | "evaluate";

/**
 * Candidate detail BODY — a CV-first, tabbed recruiter surface:
 *  - CV: the candidate's ORIGINAL CV, rendered inline (clean, not a derived
 *    doc) so a recruiter reviews the real résumé; a Download button pulls the
 *    original file. CV access is audit-logged.
 *  - Application: the cover letter + screening answers the candidate actually
 *    submitted — read before deciding.
 *  - Evaluate: the on-demand, recruiter-style AI CV evaluation (explicit click).
 *
 * Identity, the match ring, prev/next, and the review/reject decision live in
 * the sheet header + footer. No auto "why this match" reasons text.
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
  const [tab, setTab] = React.useState<DetailTab>("cv");

  const cv = app.cv ?? null;
  const answers = React.useMemo(
    () => Object.entries(app.screening_answers ?? {}),
    [app.screening_answers],
  );
  const answerCount = answers.length + (app.cover_letter ? 1 : 0);

  const tabs: { id: DetailTab; label: string; icon: typeof FileText; badge?: number }[] = [
    { id: "cv", label: t("cvTabDocument"), icon: FileText },
    {
      id: "application",
      label: t("cvTabApplication"),
      icon: ClipboardList,
      badge: answerCount || undefined,
    },
    { id: "evaluate", label: t("cvTabEvaluation"), icon: Sparkles },
  ];

  return (
    <div className={cn("flex min-h-0 flex-col", tab === "cv" && "h-full")}>
      {/* Rejection outcome (partner-only reason + note) — read-only context. */}
      {app.status === "rejected" && app.rejection_reason && (
        <div className="shrink-0 border-b border-border px-5 py-3">
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

      {/* Segmented tab bar */}
      <div
        role="tablist"
        aria-label={t("detailTabsLabel")}
        className="sticky top-0 z-10 flex shrink-0 items-center gap-1 border-b border-border bg-card px-3"
      >
        {tabs.map(({ id, label, icon: Icon, badge }) => {
          const active = tab === id;
          return (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setTab(id)}
              className={cn(
                "-mb-px inline-flex items-center gap-1.5 border-b-2 px-3 py-2.5 type-small font-medium outline-none transition-colors focus-visible:text-foreground",
                active
                  ? "border-[var(--text-primary)] text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              <Icon aria-hidden className="size-4" strokeWidth={1.8} />
              {label}
              {badge != null && (
                <span className="ml-0.5 inline-flex min-w-[1.15rem] items-center justify-center rounded-full bg-[var(--bg-muted)] px-1 text-[0.625rem] font-semibold tabular-nums text-muted-foreground">
                  {badge}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* ------------------------------ CV tab ------------------------------ */}
      {tab === "cv" &&
        (cv ? (
          <div className="flex min-h-0 flex-1 flex-col">
            <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border px-5 py-2.5">
              <span className="inline-flex min-w-0 items-center gap-1.5 type-small font-medium text-foreground">
                <FileText
                  aria-hidden
                  className="size-4 shrink-0 text-muted-foreground"
                  strokeWidth={1.8}
                />
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
            <p className="flex shrink-0 items-start gap-1.5 border-t border-border px-5 py-2 type-caption text-muted-foreground">
              <ShieldCheck aria-hidden className="mt-0.5 size-3.5 shrink-0" strokeWidth={1.8} />
              {t("cvAccessNote")}
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
        ))}

      {/* -------------------------- Application tab ------------------------- */}
      {tab === "application" &&
        (app.cover_letter || answers.length > 0 ? (
          <div>
            {app.cover_letter && (
              <section className="border-b border-border px-5 py-4">
                <h4 className="mb-2 flex items-center gap-1.5 text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                  <MessageSquareText aria-hidden className="size-3.5" strokeWidth={1.9} />
                  {t("coverLetterTitle")}
                </h4>
                <p className="whitespace-pre-wrap type-small leading-relaxed text-foreground">
                  {app.cover_letter}
                </p>
              </section>
            )}
            {answers.length > 0 && (
              <section className="px-5 py-4">
                <h4 className="mb-2.5 flex items-center gap-1.5 text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                  <ClipboardList aria-hidden className="size-3.5" strokeWidth={1.9} />
                  {t("screeningAnswersTitle")}
                </h4>
                <dl className="space-y-3">
                  {answers.map(([key, value], i) => (
                    <div key={key} className="rounded-lg border border-border bg-[var(--bg-subtle)] p-3">
                      <dt className="type-caption font-semibold text-muted-foreground">
                        {isOpaqueQuestionKey(key)
                          ? t("screeningAnswerN", { n: i + 1 })
                          : key}
                      </dt>
                      <dd className="mt-1 whitespace-pre-wrap type-small text-foreground">
                        {Array.isArray(value) ? value.join(", ") : value}
                      </dd>
                    </div>
                  ))}
                </dl>
              </section>
            )}
          </div>
        ) : (
          <div className="flex min-h-[40vh] items-center justify-center p-5">
            <EmptyState
              kind="empty"
              icon={ClipboardList}
              title={t("applicationEmptyTitle")}
              description={t("applicationEmptyBody")}
            />
          </div>
        ))}

      {/* --------------------------- Evaluate tab -------------------------- */}
      {tab === "evaluate" &&
        (cv ? (
          <CvEvaluationPanel applicationId={app.id} />
        ) : (
          <div className="flex min-h-[40vh] items-center justify-center p-5">
            <EmptyState
              kind="empty"
              icon={Sparkles}
              title={t("evaluateNoCvTitle")}
              description={t("evaluateNoCvBody")}
            />
          </div>
        ))}
    </div>
  );
}
