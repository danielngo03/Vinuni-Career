"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import {
  ArrowLeft,
  MagicWand,
  Sparkle,
  Warning,
} from "@phosphor-icons/react";
import { cvApi, type CvAiSuggestion, type CvSection } from "@/lib/api/cv";
import { cn } from "@/lib/utils";
import { SpinnerIcon } from "./ai-assist/spinner-icon";
import { DiffPanel } from "./ai-assist/diff-panel";

// ── Types ─────────────────────────────────────────────────────────────────────

type TaskKey = "aiFill" | "aiRewrite" | "aiTailor" | "atsSuggest" | "fabricationCheck";

const TASK_TYPE_MAP: Record<TaskKey, string> = {
  aiFill: "fill_cv_template_from_sources",
  aiRewrite: "rewrite_cv_section",
  aiTailor: "optimize_cv_for_job",
  atsSuggest: "ats_keyword_suggestions",
  fabricationCheck: "cv_fabrication_check",
};

const TASK_GRADIENT: Record<TaskKey, string> = {
  aiFill: "from-[var(--brand-primary)] to-[var(--gray-800)]",
  aiRewrite: "from-[var(--teal-600)] to-[var(--teal-700)]",
  aiTailor: "from-[var(--gray-700)] to-[var(--gray-900)]",
  atsSuggest: "from-[var(--gray-600)] to-[var(--gray-800)]",
  fabricationCheck: "from-[var(--amber-600)] to-[var(--amber-700)]",
};

type Phase =
  | { name: "idle" }
  | { name: "pickSection"; taskKey: TaskKey }
  | { name: "requesting" }
  | { name: "processing"; suggestionId: string }
  | { name: "ready"; suggestion: CvAiSuggestion }
  | { name: "accepting"; suggestion: CvAiSuggestion }
  | { name: "failed"; message: string };

const POLL_INTERVAL_MS = 2000;
const POLL_MAX_ATTEMPTS = 15;

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
  cvId: string;
  sections?: CvSection[];
  /** When set, auto-starts polling this suggestion on mount (AI draft creation flow). */
  initialSuggestionId?: string | null;
}

export function CvAiAssistCard({ cvId, sections = [], initialSuggestionId }: Props) {
  const t = useTranslations("cv");
  const tc = useTranslations("common");

  const [phase, setPhase] = useState<Phase>({ name: "idle" });
  const [selectedSectionId, setSelectedSectionId] = useState<string>("");
  const [factConfirmed, setFactConfirmed] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollAttemptsRef = useRef(0);

  // Idempotency key resets per request so retries don't collide.
  const idempotencyRef = useRef(crypto.randomUUID());

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    pollAttemptsRef.current = 0;
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  // ── Polling ────────────────────────────────────────────────────────────────

  const startPolling = useCallback(
    (suggestionId: string) => {
      stopPolling();
      pollAttemptsRef.current = 0;
      pollRef.current = setInterval(async () => {
        pollAttemptsRef.current += 1;
        if (pollAttemptsRef.current > POLL_MAX_ATTEMPTS) {
          stopPolling();
          setPhase({ name: "failed", message: t("ai.failed") });
          return;
        }
        try {
          const s = await cvApi.getSuggestion(cvId, suggestionId);
          if (s.status === "ready") {
            stopPolling();
            setPhase({ name: "ready", suggestion: s });
          } else if (s.status === "failed" || s.status === "expired") {
            stopPolling();
            setPhase({ name: "failed", message: t("ai.failed") });
          }
          // pending / processing → keep polling
        } catch {
          // network error — keep polling up to max
        }
      }, POLL_INTERVAL_MS);
    },
    [cvId, stopPolling, t],
  );

  // Auto-start polling when the builder is opened from an AI draft creation.
  const autoStartedRef = useRef(false);
  useEffect(() => {
    if (!initialSuggestionId || autoStartedRef.current) return;
    autoStartedRef.current = true;
    setPhase({ name: "processing", suggestionId: initialSuggestionId });
    startPolling(initialSuggestionId);
  }, [initialSuggestionId, startPolling]);

  // ── Request ────────────────────────────────────────────────────────────────

  const requestSuggestion = useCallback(
    async (taskKey: TaskKey, sectionId?: string) => {
      idempotencyRef.current = crypto.randomUUID();
      setPhase({ name: "requesting" });
      setFactConfirmed(false);
      try {
        const body: Parameters<typeof cvApi.requestAiSuggestion>[1] = {
          task_type: TASK_TYPE_MAP[taskKey],
          idempotency_key: idempotencyRef.current,
          // Fill task uses the student's stored profile as a grounding source.
          source_ids: taskKey === "aiFill" ? { profile: true } : undefined,
        };
        if (sectionId) body.target_section_id = sectionId;

        const suggestion = await cvApi.requestAiSuggestion(cvId, body);

        if (suggestion.status === "ready") {
          setPhase({ name: "ready", suggestion });
        } else if (
          suggestion.status === "pending" ||
          suggestion.status === "processing"
        ) {
          setPhase({ name: "processing", suggestionId: suggestion.id });
          startPolling(suggestion.id);
        } else if (
          suggestion.status === "failed" ||
          suggestion.status === "expired"
        ) {
          setPhase({ name: "failed", message: t("ai.failed") });
        } else {
          // accepted / rejected means idempotent re-use of an old key — treat as ready
          setPhase({ name: "ready", suggestion });
        }
      } catch {
        setPhase({ name: "failed", message: t("ai.unavailable") });
      }
    },
    [cvId, startPolling, t],
  );

  const handleTaskClick = useCallback(
    (taskKey: TaskKey) => {
      if (taskKey === "aiRewrite" && sections.length > 0) {
        setSelectedSectionId(sections[0]?.id ?? "");
        setPhase({ name: "pickSection", taskKey });
        return;
      }
      void requestSuggestion(taskKey);
    },
    [sections, requestSuggestion],
  );

  const handleConfirmSection = useCallback(() => {
    if (phase.name !== "pickSection") return;
    void requestSuggestion(phase.taskKey, selectedSectionId || undefined);
  }, [phase, selectedSectionId, requestSuggestion]);

  // ── Accept / Reject ────────────────────────────────────────────────────────

  const handleAccept = useCallback(async () => {
    if (phase.name !== "ready") return;
    const suggestion = phase.suggestion;
    const needsConfirm = suggestion.diff?.requires_fact_confirmation;
    if (needsConfirm && !factConfirmed) return;

    setPhase({ name: "accepting", suggestion });
    try {
      const body: Parameters<typeof cvApi.acceptAiSuggestion>[2] = {
        idempotency_key: crypto.randomUUID(),
      };
      if (needsConfirm) body.fact_confirmation = factConfirmed;
      await cvApi.acceptAiSuggestion(cvId, suggestion.id, body);
      setPhase({ name: "idle" });
    } catch {
      setPhase({ name: "ready", suggestion });
    }
  }, [phase, cvId, factConfirmed]);

  const handleReject = useCallback(async () => {
    if (phase.name !== "ready") return;
    const suggestion = phase.suggestion;
    setPhase({ name: "idle" });
    try {
      await cvApi.rejectAiSuggestion(cvId, suggestion.id);
    } catch {
      // rejection failure is silent — user already moved on
    }
  }, [phase, cvId]);

  const reset = useCallback(() => {
    stopPolling();
    setPhase({ name: "idle" });
    setFactConfirmed(false);
  }, [stopPolling]);

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <section
      aria-label={t("ai.title")}
      className="rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] backdrop-blur-md p-5 shadow-[var(--shadow-sm)]"
    >
      {/* Header */}
      <div className="flex items-center gap-2">
        {phase.name !== "idle" && (
          <button
            type="button"
            onClick={reset}
            aria-label={tc("back")}
            className="mr-1 rounded-lg p-1 text-[var(--text-muted)] hover:bg-[var(--glass-surface-light)]"
          >
            <ArrowLeft aria-hidden weight="bold" className="size-4" />
          </button>
        )}
        <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-info shadow-sm">
          <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
        </span>
        <h3 className="text-sm font-bold text-[var(--text-primary)]">
          {t("ai.title")}
        </h3>
      </div>

      {/* ── Idle phase: task buttons ───────────────────────────────────────── */}
      {phase.name === "idle" && (
        <>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            {t("ai.body")}
          </p>
          <ul className="mt-3 space-y-2">
            {(["aiFill", "aiRewrite", "aiTailor", "atsSuggest", "fabricationCheck"] as const).map((key) => (
              <li key={key}>
                <button
                  type="button"
                  onClick={() => handleTaskClick(key)}
                  className="flex w-full items-center gap-2.5 rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] px-3 py-2.5 text-left text-sm text-[var(--text-primary)] backdrop-blur-sm transition hover:bg-[var(--glass-surface-heavy)] hover:border-[var(--brand-primary)]/60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--brand-primary)]"
                >
                  <span className={cn("flex size-6 shrink-0 items-center justify-center rounded-md bg-gradient-to-br shadow-sm", TASK_GRADIENT[key])}>
                    <MagicWand aria-hidden weight="duotone" className="size-3.5 text-white" />
                  </span>
                  {t(`ai.${key}`)}
                </button>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-[var(--text-muted)]">
            {t("ai.note")}
          </p>
        </>
      )}

      {/* ── Section picker (aiRewrite) ─────────────────────────────────────── */}
      {phase.name === "pickSection" && (
        <div className="mt-3 space-y-3">
          <p className="text-sm text-[var(--text-secondary)]">
            {t("ai.selectSection")}
          </p>
          {sections.length > 0 ? (
            <select
              value={selectedSectionId}
              onChange={(e) => setSelectedSectionId(e.target.value)}
              className="w-full rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] px-3 py-2 text-sm text-[var(--text-primary)] backdrop-blur-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--brand-primary)]"
            >
              {sections.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title}
                </option>
              ))}
            </select>
          ) : (
            <p className="text-sm text-[var(--text-muted)]">
              {t("ai.noSection")}
            </p>
          )}
          <button
            type="button"
            onClick={handleConfirmSection}
            disabled={sections.length === 0}
            className="flex w-full items-center justify-center gap-1.5 rounded-xl bg-[var(--brand-primary)] px-4 py-2 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-40"
          >
            <MagicWand aria-hidden weight="duotone" className="size-4" />
            {t(`ai.${phase.taskKey}`)}
          </button>
        </div>
      )}

      {/* ── Requesting / Processing ────────────────────────────────────────── */}
      {(phase.name === "requesting" || phase.name === "processing") && (
        <div className="mt-4 flex flex-col items-center gap-3 py-4">
          <SpinnerIcon />
          <p className="text-sm text-[var(--text-secondary)]">
            {phase.name === "requesting"
              ? t("ai.requesting")
              : t("ai.processing")}
          </p>
        </div>
      )}

      {/* ── Diff review ───────────────────────────────────────────────────── */}
      {(phase.name === "ready" || phase.name === "accepting") && (
        <DiffPanel
          suggestion={phase.suggestion}
          factConfirmed={factConfirmed}
          onFactConfirm={setFactConfirmed}
          onAccept={handleAccept}
          onReject={handleReject}
          accepting={phase.name === "accepting"}
          t={t}
        />
      )}

      {/* ── Failed ────────────────────────────────────────────────────────── */}
      {phase.name === "failed" && (
        <div className="mt-3 space-y-3">
          <div className="flex items-start gap-2 rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] px-3.5 py-3 backdrop-blur-sm">
            <Warning
              aria-hidden
              weight="fill"
              className="mt-0.5 size-4 shrink-0 text-[var(--warning)]"
            />
            <p className="text-sm text-[var(--text-secondary)]">
              {phase.message}
            </p>
          </div>
          <button
            type="button"
            onClick={reset}
            className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] backdrop-blur-sm hover:bg-[var(--glass-surface-heavy)]"
          >
            {t("ai.reject")}
          </button>
        </div>
      )}
    </section>
  );
}
