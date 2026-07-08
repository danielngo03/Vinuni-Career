"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import {
  ArrowClockwise,
  PaperPlaneRight,
  ShieldCheck,
  Sparkle,
  WarningCircle,
} from "@phosphor-icons/react";
import { cvApi, type CvAiSuggestion, type CvAiTaskType, type CvSection } from "@/lib/api/cv";
import { ApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";
import { DiffPanel } from "../ai-assist/diff-panel";
import { SpinnerIcon } from "../ai-assist/spinner-icon";

/**
 * The AI chat assistant (design spec §3 "AI"). Replaces the static
 * `CvAiAssistCard` and the floating bottom-corner AI button with a single
 * integrated chat panel: a message input + intent chips (rewrite / optimize for
 * role / ATS keywords / evidence-check). Each turn:
 *   ask → PENDING diff → readable preview → Accept (fact-confirm when required)
 *   / Reject → applied + versioned + parent refetch.
 * Non-destructive; never auto-applies. Reuses the existing endpoints
 * (`requestAiEditCommand`, `requestAiSuggestion`, `getSuggestion`,
 * `acceptAiSuggestion`, `rejectAiSuggestion`) and the shared `DiffPanel`.
 */

/** Intent chips → CV AI task types (or the free-text command). */
type Intent = "command" | "rewrite" | "optimize" | "ats" | "evidence";

const INTENT_TASK: Record<Exclude<Intent, "command" | "optimize">, CvAiTaskType> = {
  rewrite: "rewrite_cv_section",
  ats: "ats_keyword_suggestions",
  evidence: "cv_fabrication_check",
};

/** Intents that operate on a specific section (need a target). */
const SECTION_INTENTS: ReadonlySet<Intent> = new Set(["rewrite"]);

const POLL_INTERVAL_MS = 2000;
const POLL_MAX_ATTEMPTS = 15;

type ChatMessage =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "pending"; text: string }
  | { id: string; role: "diff"; suggestion: CvAiSuggestion; factConfirmed: boolean; accepting: boolean }
  | { id: string; role: "applied"; text: string }
  | { id: string; role: "dismissed"; text: string }
  | { id: string; role: "error"; text: string };

function newId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `m_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

export function AiChatPanel({
  cvId,
  sections,
  jobId,
  initialSuggestionId,
  selectedSectionId,
  onApplied,
}: {
  cvId: string;
  sections: CvSection[];
  /** Target job for "optimize for role" / ATS keywords (optional). */
  jobId?: string | null;
  /** Auto-open a pending suggestion (AI-draft creation flow). */
  initialSuggestionId?: string | null;
  /** Currently selected section (used as the rewrite/optimize target). */
  selectedSectionId?: string | null;
  /** Called after a successful accept so the parent re-hydrates the CV. */
  onApplied: () => void;
}) {
  const t = useTranslations("cv.aiChat");
  // `DiffPanel` reads `cv.ai.*` keys (diffBefore/After/accept/reject/…); it needs
  // the `cv`-scoped translator, computed once here (never inside the map).
  const tCv = useTranslations("cv");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollAttemptsRef = useRef(0);
  const autoStartedRef = useRef(false);

  const editableSections = sections.filter((s) => s.section_type !== "header");

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    pollAttemptsRef.current = 0;
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  // Auto-scroll to the newest message.
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const upsert = useCallback((msg: ChatMessage) => {
    setMessages((prev) => {
      const idx = prev.findIndex((m) => m.id === msg.id);
      if (idx === -1) return [...prev, msg];
      const next = [...prev];
      next[idx] = msg;
      return next;
    });
  }, []);

  const resolveReady = useCallback(
    (pendingId: string, suggestion: CvAiSuggestion) => {
      upsert({ id: pendingId, role: "diff", suggestion, factConfirmed: false, accepting: false });
      setBusy(false);
    },
    [upsert],
  );

  const fail = useCallback(
    (pendingId: string, message: string) => {
      upsert({ id: pendingId, role: "error", text: message });
      setBusy(false);
    },
    [upsert],
  );

  const startPolling = useCallback(
    (pendingId: string, suggestionId: string) => {
      stopPolling();
      pollAttemptsRef.current = 0;
      pollRef.current = setInterval(async () => {
        pollAttemptsRef.current += 1;
        if (pollAttemptsRef.current > POLL_MAX_ATTEMPTS) {
          stopPolling();
          fail(pendingId, t("failed"));
          return;
        }
        try {
          const s = await cvApi.getSuggestion(cvId, suggestionId);
          if (s.status === "ready") {
            stopPolling();
            resolveReady(pendingId, s);
          } else if (s.status === "failed" || s.status === "expired") {
            stopPolling();
            fail(pendingId, t("failed"));
          }
        } catch {
          /* keep polling up to max */
        }
      }, POLL_INTERVAL_MS);
    },
    [cvId, stopPolling, fail, resolveReady, t],
  );

  const handleSuggestionResult = useCallback(
    (pendingId: string, suggestion: CvAiSuggestion) => {
      if (suggestion.status === "ready") {
        resolveReady(pendingId, suggestion);
      } else if (suggestion.status === "pending" || suggestion.status === "processing") {
        startPolling(pendingId, suggestion.id);
      } else if (suggestion.status === "failed" || suggestion.status === "expired") {
        fail(pendingId, t("failed"));
      } else {
        // accepted/rejected (idempotent replay) — show as-is.
        resolveReady(pendingId, suggestion);
      }
    },
    [resolveReady, startPolling, fail, t],
  );

  // Auto-start a pending suggestion (AI-draft creation).
  useEffect(() => {
    if (!initialSuggestionId || autoStartedRef.current) return;
    autoStartedRef.current = true;
    const pendingId = newId();
    setBusy(true);
    upsert({ id: newId(), role: "user", text: t("draftKickoff") });
    upsert({ id: pendingId, role: "pending", text: t("thinking") });
    startPolling(pendingId, initialSuggestionId);
  }, [initialSuggestionId, startPolling, upsert, t]);

  const targetSectionId = useCallback((): string | undefined => {
    if (selectedSectionId && editableSections.some((s) => s.id === selectedSectionId)) {
      return selectedSectionId;
    }
    return editableSections[0]?.id;
  }, [selectedSectionId, editableSections]);

  const run = useCallback(
    async (intent: Intent, text: string) => {
      if (busy) return;
      const userText =
        intent === "command"
          ? text
          : t(`intentSent.${intent}`);
      const pendingId = newId();
      setBusy(true);
      upsert({ id: newId(), role: "user", text: userText });
      upsert({ id: pendingId, role: "pending", text: t("thinking") });

      try {
        let suggestion: CvAiSuggestion;
        if (intent === "command") {
          suggestion = await cvApi.requestAiEditCommand(cvId, {
            instruction: text,
            target_section_id: targetSectionId() ?? null,
            idempotency_key: newId(),
          });
        } else if (intent === "optimize") {
          suggestion = await cvApi.requestAiSuggestion(cvId, {
            task_type: "optimize_cv_for_job",
            job_id: jobId ?? null,
            target_section_id: targetSectionId() ?? null,
            idempotency_key: newId(),
          });
        } else {
          const task = INTENT_TASK[intent];
          suggestion = await cvApi.requestAiSuggestion(cvId, {
            task_type: task,
            job_id: intent === "ats" ? (jobId ?? null) : null,
            target_section_id: SECTION_INTENTS.has(intent) ? (targetSectionId() ?? null) : null,
            idempotency_key: newId(),
          });
        }
        handleSuggestionResult(pendingId, suggestion);
      } catch (e) {
        const message =
          e instanceof ApiError && e.code === "AI_UNAVAILABLE" ? t("unavailable") : t("failed");
        fail(pendingId, message);
      }
    },
    [busy, cvId, jobId, targetSectionId, handleSuggestionResult, fail, upsert, t],
  );

  const submitInput = useCallback(() => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    void run("command", text);
  }, [input, busy, run]);

  // ---- Accept / reject a pending diff ----
  const acceptDiff = useCallback(
    async (msgId: string, suggestion: CvAiSuggestion, factConfirmed: boolean) => {
      const needsConfirm = suggestion.diff?.requires_fact_confirmation;
      if (needsConfirm && !factConfirmed) return;
      upsert({ id: msgId, role: "diff", suggestion, factConfirmed, accepting: true });
      try {
        await cvApi.acceptAiSuggestion(cvId, suggestion.id, {
          idempotency_key: newId(),
          ...(needsConfirm ? { fact_confirmation: factConfirmed } : {}),
        });
        upsert({ id: msgId, role: "applied", text: t("applied") });
        onApplied();
      } catch {
        upsert({ id: msgId, role: "diff", suggestion, factConfirmed, accepting: false });
      }
    },
    [cvId, onApplied, upsert, t],
  );

  const rejectDiff = useCallback(
    async (msgId: string, suggestion: CvAiSuggestion) => {
      upsert({ id: msgId, role: "dismissed", text: t("dismissed") });
      try {
        await cvApi.rejectAiSuggestion(cvId, suggestion.id);
      } catch {
        /* silent — the student already moved on */
      }
    },
    [cvId, upsert, t],
  );

  const setFactConfirmed = useCallback(
    (msgId: string, suggestion: CvAiSuggestion, factConfirmed: boolean) => {
      upsert({ id: msgId, role: "diff", suggestion, factConfirmed, accepting: false });
    },
    [upsert],
  );

  const INTENT_CHIPS: Intent[] = ["rewrite", "optimize", "ats", "evidence"];

  return (
    <section
      aria-label={t("title")}
      className="flex flex-col rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] shadow-[var(--shadow-sm)] backdrop-blur-md"
    >
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-[var(--glass-border)] px-4 py-3">
        <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-info shadow-sm">
          <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
        </span>
        <div className="min-w-0">
          <h3 className="text-sm font-bold text-[var(--text-primary)]">{t("title")}</h3>
        </div>
      </div>

      {/* Message stream */}
      <div
        ref={listRef}
        className="flex max-h-[26rem] min-h-[10rem] flex-col gap-3 overflow-y-auto p-4"
        aria-live="polite"
      >
        {messages.length === 0 && (
          <div className="flex flex-col items-center gap-2 py-4 text-center">
            <span className="flex size-10 items-center justify-center rounded-2xl icon-chip-info shadow-sm">
              <Sparkle aria-hidden weight="duotone" className="size-5 text-white" />
            </span>
            <p className="text-sm font-semibold text-[var(--text-primary)]">{t("emptyTitle")}</p>
            <p className="max-w-[15rem] text-xs leading-relaxed text-[var(--text-secondary)]">
              {t("emptyBody")}
            </p>
          </div>
        )}

        {messages.map((m) => {
          if (m.role === "user") {
            return (
              <div key={m.id} className="flex justify-end">
                <p className="max-w-[85%] rounded-2xl rounded-br-md bg-[var(--brand-primary)] px-3.5 py-2 text-sm text-white">
                  {m.text}
                </p>
              </div>
            );
          }
          if (m.role === "pending") {
            return (
              <div key={m.id} className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
                <SpinnerIcon />
                {m.text}
              </div>
            );
          }
          if (m.role === "applied") {
            return (
              <div
                key={m.id}
                className="flex items-center gap-2 rounded-xl border border-[var(--brand-teal)]/30 bg-[var(--teal-50)] px-3.5 py-2.5 text-sm font-medium text-[var(--teal-700)]"
              >
                <ShieldCheck aria-hidden weight="fill" className="size-4 shrink-0" />
                {m.text}
              </div>
            );
          }
          if (m.role === "dismissed") {
            return (
              <p key={m.id} className="text-xs italic text-[var(--text-muted)]">
                {m.text}
              </p>
            );
          }
          if (m.role === "error") {
            return (
              <div
                key={m.id}
                className="flex items-start gap-2 rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] px-3.5 py-2.5 text-sm text-[var(--text-secondary)]"
              >
                <WarningCircle aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0 text-[var(--warning)]" />
                {m.text}
              </div>
            );
          }
          // diff
          return (
            <div
              key={m.id}
              className="rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] p-3"
            >
              <DiffPanel
                suggestion={m.suggestion}
                factConfirmed={m.factConfirmed}
                onFactConfirm={(v) => setFactConfirmed(m.id, m.suggestion, v)}
                onAccept={() => void acceptDiff(m.id, m.suggestion, m.factConfirmed)}
                onReject={() => void rejectDiff(m.id, m.suggestion)}
                accepting={m.accepting}
                t={tCv}
              />
            </div>
          );
        })}
      </div>

      {/* Intent chips */}
      <div className="flex flex-wrap gap-1.5 border-t border-[var(--glass-border)] px-3 pt-3">
        {INTENT_CHIPS.map((intent) => (
          <button
            key={intent}
            type="button"
            disabled={busy}
            onClick={() => void run(intent, "")}
            className={cn(
              "inline-flex items-center gap-1 rounded-full border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)] outline-none transition-colors hover:border-[var(--brand-primary)]/50 hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40 disabled:cursor-not-allowed disabled:opacity-45",
            )}
          >
            {t(`intents.${intent}`)}
          </button>
        ))}
      </div>

      {/* Input */}
      <div className="p-3">
        <div className="flex items-end gap-2">
          <label htmlFor="cv-ai-chat-input" className="sr-only">
            {t("placeholder")}
          </label>
          <textarea
            id="cv-ai-chat-input"
            value={input}
            rows={1}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submitInput();
              }
            }}
            placeholder={t("placeholder")}
            disabled={busy}
            className="max-h-28 min-h-[2.5rem] w-full resize-none rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] px-3.5 py-2.5 text-sm text-[var(--text-primary)] outline-none backdrop-blur-sm transition-colors placeholder:text-[var(--text-muted)] focus:border-[var(--brand-primary)]/50 focus:bg-[var(--glass-surface-heavy)] focus:ring-2 focus:ring-[var(--brand-primary)]/30 disabled:opacity-60"
          />
          <button
            type="button"
            onClick={submitInput}
            disabled={!input.trim() || busy}
            aria-label={t("send")}
            className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-[var(--brand-primary)] text-white outline-none transition hover:opacity-90 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40 disabled:opacity-40"
          >
            {busy ? <ArrowClockwise aria-hidden weight="bold" className="size-4 animate-spin" /> : <PaperPlaneRight aria-hidden weight="fill" className="size-4" />}
          </button>
        </div>
        <p className="mt-2 flex items-start gap-1.5 text-[11px] leading-relaxed text-[var(--text-muted)]">
          <ShieldCheck aria-hidden weight="duotone" className="mt-px size-3.5 shrink-0" />
          {t("safety")}
        </p>
      </div>
    </section>
  );
}
