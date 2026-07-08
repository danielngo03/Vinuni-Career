"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CaretRight,
  ChatCircleDots,
  ClockCountdown,
  Keyboard,
  Microphone,
  WarningCircle,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, EmptyState, Skeleton } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import {
  mockInterviewApi,
  sessionListTitle,
  type MockInterviewModality,
  type MockInterviewSessionListItem,
  type MockInterviewStatus,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { CoachingReport } from "./coaching-report";
import { TranscriptReview } from "./transcript-review";

const STATUS_KEY: Record<MockInterviewStatus, string> = {
  active: "statusActive",
  completed: "statusCompleted",
  aborted: "statusAborted",
  expired: "statusExpired",
};

const STATUS_TONE: Record<MockInterviewStatus, string> = {
  active: "text-[var(--amber-700)]",
  completed: "text-[var(--teal-700)]",
  aborted: "text-[var(--text-muted)]",
  expired: "text-[var(--text-muted)]",
};

const MODALITY_KEY: Record<MockInterviewModality, string> = {
  voice: "modalityVoice",
  text: "modalityText",
  realtime: "modalityRealtime",
};

const MODALITY_ICON: Record<MockInterviewModality, typeof Microphone> = {
  voice: Microphone,
  realtime: Microphone,
  text: Keyboard,
};

/** Format seconds as m:ss (locale-neutral data). */
function formatDuration(seconds: number | null): string {
  const s = Math.max(0, Math.round(seconds ?? 0));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}:${rem.toString().padStart(2, "0")}`;
}

/**
 * Dedicated, cross-job "My interviews" surface. Lists every past mock-interview
 * session; a row opens a read-only review (coaching + transcript) for that
 * session. Real loading / empty / error states — never placeholders.
 */
export function StudentInterviewsScreen() {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (selectedId) {
    return (
      <SessionReview
        sessionId={selectedId}
        onBack={() => setSelectedId(null)}
      />
    );
  }

  return <InterviewsList onOpen={setSelectedId} />;
}

/* -------------------------------- list ---------------------------------- */

function InterviewsList({ onOpen }: { onOpen: (id: string) => void }) {
  const t = useTranslations("jobs.mockInterview");
  const locale = useLocale();

  const query = useQuery({
    queryKey: ["mock-interview", "sessions", "all"],
    queryFn: () => mockInterviewApi.listSessions(),
    retry: false,
    staleTime: 30_000,
  });

  return (
    <>
      <PageHeader title={t("myInterviewsTitle")} />
      <p className="mb-5 -mt-2 text-sm text-[var(--text-secondary)]">
        {t("myInterviewsSubtitle")}
      </p>

      <div className="mx-auto max-w-3xl">
        {query.isPending ? (
          <ul className="space-y-2.5" aria-hidden>
            {[0, 1, 2, 3].map((i) => (
              <li key={i}>
                <Skeleton className="h-[76px] w-full rounded-2xl" />
              </li>
            ))}
          </ul>
        ) : query.isError ? (
          <EmptyState
            kind="error"
            icon={WarningCircle}
            title={t("historyError")}
            action={
              <Button
                variant="secondary"
                onClick={() => query.refetch()}
                disabled={query.isFetching}
              >
                {t("historyRetry")}
              </Button>
            }
          />
        ) : query.data.length === 0 ? (
          <EmptyState
            kind="empty"
            icon={Microphone}
            title={t("myInterviewsEmptyTitle")}
            description={t("myInterviewsEmptyBody")}
            action={
              <Link href="/jobs">
                <Button variant="primary">
                  <Microphone aria-hidden weight="bold" className="size-4" />
                  {t("myInterviewsBrowseCta")}
                </Button>
              </Link>
            }
          />
        ) : (
          <>
            <p className="mb-2.5 text-xs font-medium text-[var(--text-muted)]">
              {t("myInterviewsCount", { count: query.data.length })}
            </p>
            <ul className="space-y-2.5">
              {query.data.map((item) => (
                <InterviewRow
                  key={item.id}
                  item={item}
                  locale={locale}
                  onOpen={onOpen}
                />
              ))}
            </ul>
          </>
        )}
      </div>
    </>
  );
}

function InterviewRow({
  item,
  locale,
  onOpen,
}: {
  item: MockInterviewSessionListItem;
  locale: string;
  onOpen: (id: string) => void;
}) {
  const t = useTranslations("jobs.mockInterview");
  const status: MockInterviewStatus = STATUS_KEY[item.status]
    ? item.status
    : "completed";
  const ModalityIcon = MODALITY_ICON[item.modality] ?? ChatCircleDots;
  const title = sessionListTitle(item) || t("historyUntitled");
  const date = new Date(item.created_at).toLocaleDateString(
    locale === "vi" ? "vi-VN" : "en-US",
    { day: "numeric", month: "short", year: "numeric" },
  );

  return (
    <li>
      <button
        type="button"
        onClick={() => onOpen(item.id)}
        className="marketplace-card marketplace-card-hover flex w-full items-center gap-3.5 rounded-2xl px-4 py-3.5 text-left outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
      >
        <span
          aria-hidden
          className="flex size-9 shrink-0 items-center justify-center rounded-xl icon-chip-primary"
        >
          <ModalityIcon weight="duotone" className="size-[18px]" />
        </span>
        <div className="min-w-0 flex-1">
          <p
            className="truncate text-sm font-semibold text-[var(--text-primary)]"
            title={title}
          >
            {title}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-xs text-[var(--text-muted)]">
            <span>{date}</span>
            <span aria-hidden>·</span>
            <span className={cn("font-medium", STATUS_TONE[status])}>
              {t(STATUS_KEY[status])}
            </span>
            <span aria-hidden>·</span>
            <span>{t(MODALITY_KEY[item.modality] ?? "modalityText")}</span>
            {item.question_count > 0 && (
              <>
                <span aria-hidden>·</span>
                <span>{t("historyQuestions", { count: item.question_count })}</span>
              </>
            )}
            {item.duration_seconds != null && item.duration_seconds > 0 && (
              <>
                <span aria-hidden>·</span>
                <span className="inline-flex items-center gap-1 font-data">
                  <ClockCountdown aria-hidden weight="duotone" className="size-3.5" />
                  {formatDuration(item.duration_seconds)}
                </span>
              </>
            )}
          </div>
        </div>
        <span className="flex shrink-0 items-center gap-1 text-xs font-semibold text-[var(--brand-primary)]">
          {t("historyView")}
          <CaretRight aria-hidden weight="bold" className="size-3.5" />
        </span>
      </button>
    </li>
  );
}

/* ------------------------------- detail --------------------------------- */

function SessionReview({
  sessionId,
  onBack,
}: {
  sessionId: string;
  onBack: () => void;
}) {
  const t = useTranslations("jobs.mockInterview");
  const qc = useQueryClient();

  const query = useQuery({
    queryKey: ["mock-interview", "session", sessionId],
    queryFn: () => mockInterviewApi.getSession(sessionId),
    retry: false,
  });

  function handleDeleted() {
    void qc.invalidateQueries({ queryKey: ["mock-interview", "sessions"] });
    onBack();
  }

  const backButton = (
    <button
      type="button"
      onClick={onBack}
      className="mb-4 inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--text-muted)] outline-none transition-colors hover:text-[var(--text-secondary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
    >
      <ArrowLeft aria-hidden weight="bold" className="size-3.5" />
      {t("myInterviewsBackToList")}
    </button>
  );

  return (
    <div className="mx-auto max-w-2xl">
      {backButton}

      {query.isPending ? (
        <div
          className="flex min-h-[40vh] flex-col items-center justify-center gap-3"
          role="status"
        >
          <span
            aria-hidden
            className="size-8 animate-spin rounded-full border-4 border-[var(--bg-muted)] border-t-[var(--brand-primary)]"
          />
          <span className="sr-only">{t("connectingHint")}</span>
        </div>
      ) : query.isError ? (
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("myInterviewsDetailError")}
          action={
            <Button
              variant="secondary"
              onClick={() => query.refetch()}
              disabled={query.isFetching}
            >
              {t("historyRetry")}
            </Button>
          }
        />
      ) : (
        <div className="space-y-6">
          <CoachingReport report={query.data.report} />
          <TranscriptReview detail={query.data} onDeleted={handleDeleted} />
        </div>
      )}
    </div>
  );
}
