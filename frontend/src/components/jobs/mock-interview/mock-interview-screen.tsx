"use client";

import { useCallback, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ClockCounterClockwise,
  Sparkle,
  WarningCircle,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, EmptyState, useToast } from "@/components/ui";
import {
  ApiError,
  mockInterviewApi,
  type MockInterviewModality,
  type MockInterviewSession,
  type MockInterviewSessionDetail,
  type RecordTurnInput,
} from "@/lib/api";
import { CoachingReport } from "./coaching-report";
import { LiveSession } from "./live-session";
import { PreSessionSetup, type AnswerMode, type StartBlock } from "./pre-session-setup";
import { TranscriptReview } from "./transcript-review";

type Phase =
  | { name: "setup" }
  | { name: "connecting" }
  | {
      name: "live";
      session: MockInterviewSession;
      mode: AnswerMode;
      serverVoice: boolean;
      realtimeRelay: boolean;
    }
  | { name: "ending" }
  | { name: "report"; detail: MockInterviewSessionDetail }
  | { name: "error" };

function readString(details: Record<string, unknown> | undefined, key: string): string | undefined {
  const v = details?.[key];
  return typeof v === "string" ? v : undefined;
}

/** Map a createSession failure to a calm, actionable setup block. */
function toStartBlock(err: ApiError): StartBlock {
  const reason = readString(err.details, "reason");
  if (err.code === "QUOTA_EXCEEDED" || err.status === 429) {
    if (reason === "AI_WEEKLY_QUOTA_EXCEEDED") return { kind: "quota_weekly" };
    return { kind: "quota_daily" };
  }
  if (err.isConflict && reason === "ACTIVE_SESSION_EXISTS") {
    return {
      kind: "active_session",
      sessionId: readString(err.details, "session_id") ?? null,
    };
  }
  if (err.isValidation && reason === "NO_READY_CV") return { kind: "no_cv" };
  return { kind: "generic" };
}

/**
 * AI mock interview state machine:
 *   setup → connecting → live → ending → report | error
 * Owns the session, coordinates create/end, and surfaces quota/conflict/no-CV
 * as recoverable states (never a dead error).
 */
export function MockInterviewScreen({ jobId }: { jobId: string }) {
  const t = useTranslations("jobs.mockInterview");
  const locale = useLocale();
  const toast = useToast();
  const qc = useQueryClient();

  const [phase, setPhase] = useState<Phase>({ name: "setup" });
  const [startBlock, setStartBlock] = useState<StartBlock | null>(null);
  const [discarding, setDiscarding] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const endPayloadRef = useRef<{ sessionId: string; payload: { duration_seconds: number; turns?: RecordTurnInput[] } } | null>(null);

  const refreshHistory = useCallback(() => {
    void qc.invalidateQueries({ queryKey: ["mock-interview", "sessions"] });
  }, [qc]);

  const resetToSetup = useCallback(() => {
    setStartBlock(null);
    endPayloadRef.current = null;
    setPhase({ name: "setup" });
    refreshHistory();
  }, [refreshHistory]);

  const handleStart = useCallback(
    async ({
      cvId,
      mode,
      serverVoice = false,
      realtimeRelay = false,
    }: {
      cvId: string | null;
      mode: AnswerMode;
      serverVoice?: boolean;
      realtimeRelay?: boolean;
    }) => {
      setStartBlock(null);
      setPhase({ name: "connecting" });
      try {
        // Prefer the true full-duplex realtime relay for voice when available;
        // the server is authoritative and may still downgrade the modality.
        const requestedModality: MockInterviewModality =
          mode === "voice" ? (realtimeRelay ? "realtime" : "voice") : "text";
        const session = await mockInterviewApi.createSession({
          job_id: jobId,
          cv_id: cvId,
          modality: requestedModality,
          locale,
        });
        const liveMode: AnswerMode = session.modality === "text" ? "text" : mode;
        refreshHistory();
        setPhase({
          name: "live",
          session,
          mode: liveMode,
          serverVoice,
          realtimeRelay: session.modality === "realtime",
        });
      } catch (err) {
        if (err instanceof ApiError && err.code !== "NETWORK_ERROR") {
          setStartBlock(toStartBlock(err));
          setPhase({ name: "setup" });
        } else {
          setPhase({ name: "error" });
        }
      }
    },
    [jobId, locale, refreshHistory],
  );

  const handleRequestEnd = useCallback(
    async (session: MockInterviewSession, payload: { duration_seconds: number; turns?: RecordTurnInput[] }) => {
      endPayloadRef.current = { sessionId: session.session_id, payload };
      setPhase({ name: "ending" });
      try {
        const detail = await mockInterviewApi.endSession(session.session_id, payload);
        refreshHistory();
        setPhase({ name: "report", detail });
      } catch {
        setPhase({ name: "error" });
      }
    },
    [refreshHistory],
  );

  const retryEnd = useCallback(async () => {
    const pending = endPayloadRef.current;
    if (!pending) {
      resetToSetup();
      return;
    }
    setPhase({ name: "ending" });
    try {
      const detail = await mockInterviewApi.endSession(pending.sessionId, pending.payload);
      refreshHistory();
      setPhase({ name: "report", detail });
    } catch {
      setPhase({ name: "error" });
    }
  }, [refreshHistory, resetToSetup]);

  const openSession = useCallback(
    async (sessionId: string) => {
      setLoadingDetail(true);
      try {
        const detail = await mockInterviewApi.getSession(sessionId);
        setPhase({ name: "report", detail });
      } catch {
        toast.show({ tone: "error", title: t("screenErrorBody") });
      } finally {
        setLoadingDetail(false);
      }
    },
    [t, toast],
  );

  const discardActive = useCallback(async () => {
    if (startBlock?.kind !== "active_session" || !startBlock.sessionId) return;
    setDiscarding(true);
    try {
      await mockInterviewApi.abortSession(startBlock.sessionId);
      setStartBlock(null);
      refreshHistory();
    } catch {
      toast.show({ tone: "error", title: t("screenErrorBody") });
    } finally {
      setDiscarding(false);
    }
  }, [startBlock, refreshHistory, t, toast]);

  const backLink = (
    <Link
      href={`/jobs/${jobId}`}
      className="mb-4 inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--text-muted)] outline-none transition-colors hover:text-[var(--text-secondary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
    >
      <ArrowLeft aria-hidden weight="bold" className="size-3.5" />
      {t("backToJob")}
    </Link>
  );

  /* --------------------------------- views -------------------------------- */

  if (phase.name === "connecting") {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-4 text-center">
        <span className="flex size-14 items-center justify-center rounded-2xl icon-chip-primary">
          <Sparkle aria-hidden weight="duotone" className="size-7 animate-pulse" />
        </span>
        <div>
          <h1 className="text-lg font-bold text-[var(--text-primary)]">{t("connectingTitle")}</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">{t("connectingHint")}</p>
        </div>
      </div>
    );
  }

  if (phase.name === "live") {
    return (
      <LiveSession
        session={phase.session}
        mode={phase.mode}
        locale={locale}
        serverVoice={phase.serverVoice}
        realtimeRelay={phase.realtimeRelay}
        onRequestEnd={(payload) => void handleRequestEnd(phase.session, payload)}
      />
    );
  }

  if (phase.name === "ending") {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-4 text-center">
        <span
          aria-hidden
          className="size-9 animate-spin rounded-full border-4 border-[var(--bg-muted)] border-t-[var(--brand-primary)]"
        />
        <p className="text-sm font-semibold text-[var(--text-secondary)]">{t("endingLabel")}</p>
      </div>
    );
  }

  if (phase.name === "report") {
    return (
      <div className="mx-auto max-w-2xl px-4 py-8 lg:py-10">
        {backLink}
        <div className="space-y-6">
          <CoachingReport
            report={phase.detail.report}
            coverage={phase.detail.coverage}
            jobTitle={phase.detail.job_title}
            completedAt={phase.detail.ended_at}
          />
          <TranscriptReview detail={phase.detail} onDeleted={resetToSetup} />
          <div className="flex flex-col gap-4 border-t border-[var(--border-default)] pt-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <Button variant="secondary" onClick={resetToSetup}>
                {t("backToSetup")}
              </Button>
              <Button variant="primary" onClick={resetToSetup}>
                <Sparkle aria-hidden weight="bold" className="size-4" />
                {t("practiceAgain")}
              </Button>
            </div>
            <Link
              href="/student/interviews"
              className="inline-flex items-center gap-1.5 self-center rounded text-xs font-semibold text-[var(--brand-primary)] outline-none transition-colors hover:underline focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
            >
              <ClockCounterClockwise aria-hidden weight="bold" className="size-3.5" />
              {t("viewHistoryCta")}
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (phase.name === "error") {
    return (
      <div className="mx-auto max-w-2xl px-4 py-10">
        {backLink}
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("screenErrorTitle")}
          description={t("screenErrorBody")}
          action={
            <div className="flex flex-wrap items-center justify-center gap-3">
              <Button variant="secondary" onClick={resetToSetup}>
                {t("backToSetup")}
              </Button>
              <Button variant="primary" onClick={() => void retryEnd()}>
                {t("screenErrorRetry")}
              </Button>
            </div>
          }
        />
      </div>
    );
  }

  // setup
  return (
    <div className="relative">
      <div className="mx-auto max-w-2xl px-4 pt-6">{backLink}</div>
      <PreSessionSetup
        jobId={jobId}
        locale={locale}
        starting={false}
        startBlock={startBlock}
        onStart={(opts) => void handleStart(opts)}
        onOpenSession={(id) => void openSession(id)}
        onResumeActive={(id) => (id ? void openSession(id) : undefined)}
        onDiscardActive={() => void discardActive()}
        discarding={discarding}
      />
      {loadingDetail && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-[var(--surface-overlay)] backdrop-blur-sm">
          <span
            aria-hidden
            className="size-9 animate-spin rounded-full border-4 border-[var(--bg-muted)] border-t-[var(--brand-primary)]"
          />
          <span className="sr-only">{t("connectingHint")}</span>
        </div>
      )}
    </div>
  );
}
