"use client";

import { useTranslations } from "next-intl";
import { CheckCircle, Warning, X } from "@phosphor-icons/react";
import type { CvAiSuggestion } from "@/lib/api/cv";
import { sectionsToText } from "./utils";
import { SpinnerIcon } from "./spinner-icon";

interface DiffPanelProps {
  suggestion: CvAiSuggestion;
  factConfirmed: boolean;
  onFactConfirm: (v: boolean) => void;
  onAccept: () => void;
  onReject: () => void;
  accepting: boolean;
  t: ReturnType<typeof useTranslations>;
}

export function DiffPanel({
  suggestion,
  factConfirmed,
  onFactConfirm,
  onAccept,
  onReject,
  accepting,
  t,
}: DiffPanelProps) {
  const diff = suggestion.diff;
  const isAdvisory = diff?.applicable === false;
  const needsConfirm = diff?.requires_fact_confirmation ?? false;
  const canAccept = !needsConfirm || factConfirmed;

  if (isAdvisory) {
    const keywords = diff?.keywords ?? [];
    const claims = diff?.unsupported_claims ?? [];
    return (
      <div className="mt-3 space-y-3">
        {diff?.summary && (
          <div className="rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] px-3.5 py-3 backdrop-blur-sm">
            <div className="flex items-start gap-2">
              <CheckCircle
                aria-hidden
                weight="duotone"
                className="mt-0.5 size-4 shrink-0 text-[var(--brand-primary)]"
              />
              <p className="text-sm text-[var(--text-secondary)]">{diff.summary}</p>
            </div>
          </div>
        )}

        {keywords.length > 0 && (
          <div className="space-y-1.5">
            <span className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
              {t("ai.atsKeywords")}
            </span>
            <div className="flex flex-wrap gap-1.5">
              {keywords.map((kw) => (
                <span
                  key={kw}
                  className="rounded-full border border-[var(--brand-primary)]/30 bg-[var(--brand-primary)]/8 px-2 py-0.5 text-xs font-medium text-[var(--brand-primary)]"
                >
                  {kw}
                </span>
              ))}
            </div>
          </div>
        )}

        {claims.length > 0 && (
          <div className="space-y-1.5">
            <span className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
              {t("ai.fabricationClaims")}
            </span>
            <ul className="space-y-1">
              {claims.map((c, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 rounded-lg border border-[var(--warning)]/30 bg-[var(--warning)]/5 px-3 py-2 text-sm text-[var(--text-secondary)]"
                >
                  <Warning
                    aria-hidden
                    weight="fill"
                    className="mt-0.5 size-3.5 shrink-0 text-[var(--warning)]"
                  />
                  {c}
                </li>
              ))}
            </ul>
          </div>
        )}

        <button
          type="button"
          onClick={onReject}
          className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] backdrop-blur-sm transition hover:bg-[var(--glass-surface-heavy)]"
        >
          <X aria-hidden weight="bold" className="size-3.5" />
          {t("ai.dismiss")}
        </button>
      </div>
    );
  }

  const beforeText = sectionsToText(diff?.before);
  const afterText = sectionsToText(diff?.after);

  return (
    <div className="mt-3 space-y-3">
      {/* Summary */}
      {diff?.summary && (
        <div className="rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] px-3.5 py-3 backdrop-blur-sm">
          <div className="flex items-start gap-2">
            <CheckCircle
              aria-hidden
              weight="duotone"
              className="mt-0.5 size-4 shrink-0 text-[var(--brand-primary)]"
            />
            <p className="text-sm text-[var(--text-secondary)]">{diff.summary}</p>
          </div>
        </div>
      )}

      {/* Before */}
      {beforeText && (
        <div className="space-y-1">
          <span className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("ai.diffBefore")}
          </span>
          <div className="max-h-32 overflow-y-auto rounded-xl border border-[var(--glass-border)] bg-[var(--glass-surface-light)] px-3 py-2.5 text-sm text-[var(--text-secondary)] backdrop-blur-sm">
            <pre className="whitespace-pre-wrap break-words font-sans line-through opacity-60">
              {beforeText}
            </pre>
          </div>
        </div>
      )}

      {/* After */}
      {afterText && (
        <div className="space-y-1">
          <span className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("ai.diffAfter")}
          </span>
          <div className="max-h-40 overflow-y-auto rounded-xl border border-[var(--brand-primary)]/40 bg-[var(--glass-surface-light)] px-3 py-2.5 text-sm text-[var(--text-primary)] backdrop-blur-sm ring-1 ring-inset ring-[var(--brand-primary)]/20">
            <pre className="whitespace-pre-wrap break-words font-sans">
              {afterText}
            </pre>
          </div>
        </div>
      )}

      {/* Fact confirmation */}
      {needsConfirm && (
        <label className="flex cursor-pointer items-start gap-2.5 rounded-xl border border-[var(--warning)]/40 bg-[var(--warning)]/5 px-3.5 py-3">
          <input
            type="checkbox"
            checked={factConfirmed}
            onChange={(e) => onFactConfirm(e.target.checked)}
            className="mt-0.5 size-4 shrink-0 rounded accent-[var(--brand-primary)]"
          />
          <span className="text-sm text-[var(--text-secondary)]">
            {t("ai.factConfirm")}
          </span>
        </label>
      )}

      {/* Actions */}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onReject}
          disabled={accepting}
          className="flex items-center gap-1.5 rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] backdrop-blur-sm transition hover:bg-[var(--glass-surface-heavy)] disabled:opacity-40"
        >
          <X aria-hidden weight="bold" className="size-3.5" />
          {t("ai.reject")}
        </button>
        <button
          type="button"
          onClick={onAccept}
          disabled={!canAccept || accepting}
          className="flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-[var(--brand-primary)] px-4 py-2 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-40"
        >
          {accepting ? (
            <>
              <SpinnerIcon />
              {t("ai.accepting")}
            </>
          ) : (
            <>
              <CheckCircle aria-hidden weight="duotone" className="size-4" />
              {t("ai.accept")}
            </>
          )}
        </button>
      </div>
    </div>
  );
}
