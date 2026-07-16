"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import {
  Translate,
  ArrowCounterClockwise,
  Sparkle,
  Warning,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import {
  jobsApi,
  type JobTranslation,
  type JobInlineTranslation,
} from "@/lib/api";

interface TranslateJobBannerProps {
  jobId: string;
  jobLanguageCode: string;
  /**
   * Pre-warmed translation inlined by the backend (opposite of the JD language).
   * When it targets this viewer's locale, the toggle is INSTANT — no network.
   */
  inline?: JobInlineTranslation | null;
  onTranslated: (t: JobTranslation | null) => void;
  translated: boolean;
  className?: string;
}

/**
 * Compact language toggle shown when the JD language differs from the UI locale.
 * Prefers the pre-warmed inline translation (instant client-side swap); falls
 * back to the on-demand translate endpoint only when no inline copy is ready.
 */
export function TranslateJobBanner({
  jobId,
  jobLanguageCode,
  inline,
  onTranslated,
  translated,
  className,
}: TranslateJobBannerProps) {
  const t = useTranslations("jobs.translate");
  const locale = useLocale();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<"unavailable" | "failed" | null>(null);

  const targetLang = locale === "vi" ? "vi" : "en";
  const sourceLang = jobLanguageCode === "mixed" ? "en" : jobLanguageCode;
  const needsTranslation =
    sourceLang !== targetLang &&
    sourceLang !== "unknown" &&
    (targetLang === "vi" || targetLang === "en");

  if (!needsTranslation) return null;

  // The inline copy only helps when it targets this viewer's locale.
  const inlineForMe = inline && inline.target_lang === targetLang ? inline : null;

  const langLabel: Record<string, string> = {
    vi: t("languageNames.vi"),
    en: t("languageNames.en"),
    ja: t("languageNames.ja"),
    ko: t("languageNames.ko"),
    zh: t("languageNames.zh"),
    mixed: t("languageNames.mixed"),
  };

  async function handleTranslate() {
    setError(null);
    // Instant path — the translation is already in the payload.
    if (inlineForMe) {
      onTranslated({
        title: inlineForMe.title,
        description: inlineForMe.description,
        requirements: inlineForMe.requirements,
        benefits: inlineForMe.benefits,
        language_code: sourceLang,
        target_lang: targetLang,
        from_cache: true,
      });
      return;
    }
    // Fallback — fetch on demand (first-ever view before the cache warmed).
    setLoading(true);
    try {
      const result = await jobsApi.translateJd(jobId, targetLang);
      onTranslated(result);
    } catch (err: unknown) {
      const status = (err as { status?: number })?.status;
      setError(status === 503 ? "unavailable" : "failed");
    } finally {
      setLoading(false);
    }
  }

  function handleRevert() {
    setError(null);
    onTranslated(null);
  }

  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-xl border border-[var(--border-default)] bg-[var(--surface-secondary)] px-3.5 py-2.5",
        className,
      )}
      aria-live="polite"
    >
      <div className="flex min-w-0 items-center gap-2 text-[0.8125rem] leading-5">
        {translated ? (
          <>
            <span className="inline-flex items-center gap-1 rounded-md bg-[var(--content-ai-soft)] px-1.5 py-0.5 text-[0.6875rem] font-semibold text-[var(--content-ai)]">
              <Sparkle aria-hidden weight="fill" className="size-3" />
              {t("aiTag")}
            </span>
            <span className="truncate text-[var(--text-muted)]">{t("aiDisclaimer")}</span>
          </>
        ) : (
          <span className="inline-flex items-center gap-1.5 text-[var(--text-muted)]">
            <Translate aria-hidden weight="duotone" className="size-4 shrink-0" />
            {t("sourceLabel", { lang: langLabel[sourceLang] ?? sourceLang })}
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        {error && (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-[var(--brand-red)]">
            <Warning aria-hidden weight="duotone" className="size-3.5" />
            {error === "unavailable" ? t("unavailable") : t("failed")}
          </span>
        )}
        {translated ? (
          <button
            type="button"
            onClick={handleRevert}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold text-[var(--text-secondary)] outline-none transition-colors hover:bg-[var(--surface-card)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
          >
            <ArrowCounterClockwise aria-hidden weight="bold" className="size-3.5" />
            {t("viewOriginal")}
          </button>
        ) : (
          <button
            type="button"
            onClick={handleTranslate}
            disabled={loading}
            className={cn(
              "inline-flex shrink-0 items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30",
              loading
                ? "cursor-wait border-[var(--border-default)] text-[var(--text-muted)]"
                : "border-[var(--brand-primary)]/30 text-[var(--brand-primary)] hover:bg-[var(--content-ai-soft)]",
            )}
          >
            <Translate
              aria-hidden
              weight="bold"
              className={cn("size-3.5", loading && "animate-spin")}
            />
            {loading ? t("translating") : t("viewIn", { lang: langLabel[targetLang] })}
          </button>
        )}
      </div>
    </div>
  );
}
