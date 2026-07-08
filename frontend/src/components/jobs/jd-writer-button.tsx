"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import {
  CheckCircle,
  Sparkle,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { jobsApi, type JdDraftInputs } from "@/lib/api";
import { Button, Modal, useToast } from "@/components/ui";

interface Props {
  /** When present, uses the anchored endpoint; otherwise uses standalone. */
  jobId?: string;
  /** Current form values to pass as context inputs. */
  formInputs: JdDraftInputs;
  /** Called with the accepted draft text so the parent can fill the field. */
  onAccept: (draft: string) => void;
  /** Optional visual override when used in a toolbar/header. */
  className?: string;
  /** Runs a sweep highlight across the full button surface. */
  shimmer?: boolean;
}

type Phase =
  | { name: "idle" }
  | { name: "loading" }
  | { name: "ready"; draft: string };

/**
 * "Generate with AI" button + inline draft review for the JD description field.
 * Advisory only — partners review and explicitly accept before the draft fills
 * the form. No auto-apply, no publish without confirmation.
 */
export function JdWriterButton({
  jobId,
  formInputs,
  onAccept,
  className,
  shimmer = false,
}: Props) {
  const t = useTranslations("jobs.aiJd");
  const toast = useToast();
  const [phase, setPhase] = useState<Phase>({ name: "idle" });

  async function generate() {
    setPhase({ name: "loading" });
    try {
      const result = jobId
        ? await jobsApi.aiDraftDescription(jobId, formInputs)
        : await jobsApi.aiDraftDescriptionStandalone(formInputs);
      setPhase({ name: "ready", draft: result.draft });
    } catch {
      toast.show({ tone: "error", title: t("error") });
      setPhase({ name: "idle" });
    }
  }

  function handleAccept() {
    if (phase.name !== "ready") return;
    onAccept(phase.draft);
    setPhase({ name: "idle" });
  }

  return (
    <>
      <button
        type="button"
        onClick={generate}
        disabled={phase.name === "loading"}
        className={cn(
          "relative inline-flex items-center justify-center overflow-hidden rounded-full border border-[var(--ai-accent)]/15 bg-[var(--text-primary)] px-4 py-2.5 text-sm font-semibold text-white transition hover:opacity-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ai-accent)]/30 disabled:cursor-not-allowed disabled:opacity-60",
          className,
        )}
      >
        {shimmer && phase.name === "idle" && (
          <span aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden rounded-[inherit]">
            <span
              className="absolute inset-y-0 -left-1/2 w-1/2 bg-[linear-gradient(110deg,transparent_0%,rgba(255,255,255,0.08)_35%,rgba(255,255,255,0.55)_50%,rgba(255,255,255,0.08)_65%,transparent_100%)] motion-reduce:hidden"
              style={{ animation: "jobAiSweep 2.8s linear infinite" }}
            />
          </span>
        )}
        <span className="relative flex items-center gap-2">
          {phase.name === "loading" ? (
            <svg
              aria-hidden
              className="size-4 animate-spin"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : (
            <Sparkle aria-hidden weight="duotone" className="size-4" />
          )}
          {phase.name === "loading" ? t("generating") : t("generate")}
        </span>
      </button>

      <Modal
        open={phase.name === "ready"}
        onClose={() => setPhase({ name: "idle" })}
        title={t("draftTitle")}
        size="lg"
        closeLabel={t("discard")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setPhase({ name: "idle" })}>
              {t("discard")}
            </Button>
            <Button variant="primary" onClick={handleAccept}>
              <CheckCircle aria-hidden weight="duotone" className="size-4" />
              {t("useDraft")}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <pre className="max-h-[24rem] overflow-y-auto whitespace-pre-wrap break-words rounded-2xl border border-[var(--border-default)] bg-[var(--bg-subtle)] px-4 py-4 font-sans text-sm leading-6 text-[var(--text-secondary)]">
            {phase.name === "ready" ? phase.draft : ""}
          </pre>
          <p className="text-xs leading-5 text-[var(--text-muted)]">{t("disclaimer")}</p>
        </div>
      </Modal>

      {shimmer && (
        <style jsx>{`
          @keyframes jobAiSweep {
            0% {
              transform: translateX(-160%);
            }
            100% {
              transform: translateX(340%);
            }
          }
        `}</style>
      )}
    </>
  );
}
