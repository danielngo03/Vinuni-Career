"use client";

import { useCallback, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { MagicWand, ShieldCheck, Sparkle } from "@phosphor-icons/react";
import { cvApi, type CvAiSuggestion } from "@/lib/api/cv";
import { ApiError } from "@/lib/api/errors";
import { DiffPanel } from "../ai-assist/diff-panel";
import { cn } from "@/lib/utils";

type Phase =
  | { name: "idle" }
  | { name: "requesting" }
  | { name: "ready"; suggestion: CvAiSuggestion }
  | { name: "accepting"; suggestion: CvAiSuggestion }
  | { name: "failed"; message: string };

/**
 * Natural-language AI edit command bar (`docs/CV_STUDIO_SPEC.md`
 * "Natural-Language AI Editing"): a free-text instruction always produces a
 * pending structured diff overlay the student must explicitly accept/reject —
 * it NEVER mutates the CV on its own. Reuses the same `DiffPanel` as the
 * task-based AI assistant so accept/reject/fact-confirmation behavior is
 * identical everywhere in CV Studio.
 */
export function CvAiCommandBar({
  cvId,
  onApplied,
  className,
}: {
  cvId: string;
  /** Called after a successful accept so the parent re-hydrates the CV. */
  onApplied: () => void;
  className?: string;
}) {
  const t = useTranslations("cv");
  const [instruction, setInstruction] = useState("");
  const [phase, setPhase] = useState<Phase>({ name: "idle" });
  const [factConfirmed, setFactConfirmed] = useState(false);
  const idempotencyRef = useRef(crypto.randomUUID());

  const submit = useCallback(async () => {
    const text = instruction.trim();
    if (!text) return;
    idempotencyRef.current = crypto.randomUUID();
    setPhase({ name: "requesting" });
    setFactConfirmed(false);
    try {
      const suggestion = await cvApi.requestAiEditCommand(cvId, {
        instruction: text,
        idempotency_key: idempotencyRef.current,
      });
      setPhase({ name: "ready", suggestion });
    } catch (e) {
      const message =
        e instanceof ApiError && e.code === "AI_UNAVAILABLE"
          ? t("ai.unavailable")
          : t("ai.failed");
      setPhase({ name: "failed", message });
    }
  }, [cvId, instruction, t]);

  const handleAccept = useCallback(async () => {
    if (phase.name !== "ready") return;
    const suggestion = phase.suggestion;
    const needsConfirm = suggestion.diff?.requires_fact_confirmation;
    if (needsConfirm && !factConfirmed) return;
    setPhase({ name: "accepting", suggestion });
    try {
      await cvApi.acceptAiSuggestion(cvId, suggestion.id, {
        idempotency_key: crypto.randomUUID(),
        ...(needsConfirm ? { fact_confirmation: factConfirmed } : {}),
      });
      setPhase({ name: "idle" });
      setInstruction("");
      onApplied();
    } catch {
      setPhase({ name: "ready", suggestion });
    }
  }, [phase, cvId, factConfirmed, onApplied]);

  const handleReject = useCallback(async () => {
    if (phase.name !== "ready") return;
    const suggestion = phase.suggestion;
    setPhase({ name: "idle" });
    try {
      await cvApi.rejectAiSuggestion(cvId, suggestion.id);
    } catch {
      /* rejection failure is silent — the student already moved on */
    }
  }, [phase, cvId]);

  return (
    <section
      aria-label={t("canvas.aiCommandTitle")}
      className={cn(
        "rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] backdrop-blur-md p-4 shadow-[var(--shadow-sm)]",
        className,
      )}
    >
      <div className="flex items-center gap-2">
        <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-info shadow-sm">
          <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
        </span>
        <h3 className="text-sm font-bold text-[var(--text-primary)]">
          {t("canvas.aiCommandTitle")}
        </h3>
      </div>

      {phase.name === "idle" || phase.name === "requesting" || phase.name === "failed" ? (
        <>
          <p className="mt-2 text-xs text-[var(--text-secondary)]">
            {t("canvas.aiCommandBody")}
          </p>
          <div className="mt-3 flex gap-2">
            <label htmlFor="cv-ai-command-input" className="sr-only">
              {t("canvas.aiCommandPlaceholder")}
            </label>
            <input
              id="cv-ai-command-input"
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void submit();
                }
              }}
              placeholder={t("canvas.aiCommandPlaceholder")}
              disabled={phase.name === "requesting"}
              className="w-full rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] px-3.5 py-2.5 text-sm text-[var(--text-primary)] outline-none backdrop-blur-sm transition-colors placeholder:text-[var(--text-muted)] focus:border-[var(--brand-primary)]/50 focus:bg-[var(--glass-surface-heavy)] focus:ring-2 focus:ring-[var(--brand-primary)]/30"
            />
            <button
              type="button"
              onClick={() => void submit()}
              disabled={!instruction.trim() || phase.name === "requesting"}
              aria-label={t("canvas.aiCommandSubmit")}
              className="flex shrink-0 items-center justify-center rounded-xl bg-[var(--brand-primary)] px-3.5 text-white transition hover:opacity-90 disabled:opacity-40"
            >
              <MagicWand aria-hidden weight="duotone" className="size-4" />
            </button>
          </div>
          {phase.name === "requesting" && (
            <p className="mt-2 text-xs text-[var(--text-secondary)]">{t("ai.requesting")}</p>
          )}
          {phase.name === "failed" && (
            <p className="mt-2 text-xs text-[var(--brand-red)]">{phase.message}</p>
          )}
          <p className="mt-3 flex items-start gap-1.5 text-[11px] leading-relaxed text-[var(--text-muted)]">
            <ShieldCheck aria-hidden weight="duotone" className="mt-px size-3.5 shrink-0" />
            {t("canvas.aiCommandSafety")}
          </p>
        </>
      ) : (
        <DiffPanel
          suggestion={phase.suggestion}
          factConfirmed={factConfirmed}
          onFactConfirm={setFactConfirmed}
          onAccept={() => void handleAccept()}
          onReject={() => void handleReject()}
          accepting={phase.name === "accepting"}
          t={t}
        />
      )}
    </section>
  );
}
