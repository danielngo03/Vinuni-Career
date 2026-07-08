"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { ChatCircleDots, TrashSimple, UserSound } from "@phosphor-icons/react";
import { Button, Modal, Switch, useToast } from "@/components/ui";
import {
  mockInterviewApi,
  type MockInterviewSessionDetail,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Read-only transcript for a finished session, plus two owner controls:
 * a share-to-improve-AI opt-in (persisted) and a confirmed delete.
 */
export function TranscriptReview({
  detail,
  onDeleted,
}: {
  detail: MockInterviewSessionDetail;
  onDeleted: () => void;
}) {
  const t = useTranslations("jobs.mockInterview");
  const toast = useToast();

  const [shareOptIn, setShareOptIn] = useState(detail.share_opt_in);
  const [sharePending, setSharePending] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function toggleShare(next: boolean) {
    setShareOptIn(next);
    setSharePending(true);
    try {
      await mockInterviewApi.shareSession(detail.id, next);
      toast.show({ tone: "success", title: t("shareSaved") });
    } catch {
      setShareOptIn(!next); // revert
      toast.show({ tone: "error", title: t("shareError") });
    } finally {
      setSharePending(false);
    }
  }

  async function confirmDelete() {
    setDeleting(true);
    try {
      await mockInterviewApi.deleteSession(detail.id);
      toast.show({ tone: "success", title: t("deleteSuccess") });
      setConfirmOpen(false);
      onDeleted();
    } catch {
      toast.show({ tone: "error", title: t("deleteError") });
      setDeleting(false);
    }
  }

  return (
    <section
      aria-labelledby="mi-transcript-title"
      className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)]"
    >
      <header className="flex items-start justify-between gap-3 border-b border-[var(--border-default)] px-5 py-4">
        <div className="min-w-0">
          <h2
            id="mi-transcript-title"
            className="text-base font-bold tracking-tight text-[var(--text-primary)]"
          >
            {t("transcriptTitle")}
          </h2>
          <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
            {t("transcriptSubtitle")}
          </p>
        </div>
      </header>

      <div className="px-5 py-4">
        {detail.transcript.length === 0 ? (
          <p className="py-6 text-center text-sm text-[var(--text-muted)]">
            {t("transcriptEmpty")}
          </p>
        ) : (
          <ol className="space-y-4">
            {detail.transcript.map((turn) => {
              const isInterviewer = turn.speaker === "interviewer";
              return (
                <li key={turn.seq} className="flex items-start gap-3">
                  <span
                    aria-hidden
                    className={cn(
                      "mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full",
                      isInterviewer ? "icon-chip-primary" : "icon-chip-info",
                    )}
                  >
                    {isInterviewer ? (
                      <ChatCircleDots weight="duotone" className="size-4" />
                    ) : (
                      <UserSound weight="duotone" className="size-4" />
                    )}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="kicker mb-0.5">
                      {isInterviewer ? t("interviewerLabel") : t("youLabel")}
                    </p>
                    <p className="whitespace-pre-line text-sm leading-relaxed text-[var(--text-secondary)]">
                      {turn.text}
                    </p>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </div>

      <div className="flex flex-col gap-4 border-t border-[var(--border-default)] px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <Switch
            checked={shareOptIn}
            onCheckedChange={toggleShare}
            disabled={sharePending}
            label={t("shareToggleLabel")}
            id={`mi-share-${detail.id}`}
          />
          <p className="mt-1 max-w-md text-xs leading-relaxed text-[var(--text-muted)]">
            {t("shareToggleHint")}
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setConfirmOpen(true)}
          className="shrink-0 text-[var(--brand-red)] hover:bg-[var(--red-50)] hover:text-[var(--red-700)]"
        >
          <TrashSimple aria-hidden weight="bold" className="size-4" />
          {t("deleteCta")}
        </Button>
      </div>

      <Modal
        open={confirmOpen}
        onClose={() => (deleting ? undefined : setConfirmOpen(false))}
        title={t("deleteConfirmTitle")}
        description={t("deleteConfirmBody")}
        size="sm"
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setConfirmOpen(false)}
              disabled={deleting}
            >
              {t("deleteConfirmCancel")}
            </Button>
            <Button variant="danger" onClick={confirmDelete} loading={deleting}>
              {deleting ? t("deleting") : t("deleteConfirmAction")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">
          {t("deleteConfirmBody")}
        </p>
      </Modal>
    </section>
  );
}
