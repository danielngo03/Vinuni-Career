"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import {
  Translate,
  ArrowCounterClockwise,
  Warning,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { jobsApi, type JobTranslation } from "@/lib/api";

interface TranslateJobBannerProps {
  jobId: string;
  jobLanguageCode: string;
  onTranslated: (t: JobTranslation | null) => void;
  translated: boolean;
  className?: string;
}

/** Shown when the JD language differs from the user's UI locale. */
export function TranslateJobBanner({
  jobId,
  jobLanguageCode,
  onTranslated,
  translated,
  className,
}: TranslateJobBannerProps) {
  const t = useTranslations("jobs.translate");
  const locale = useLocale();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<"unavailable" | "failed" | null>(null);

  // Only show when the JD language differs from the UI locale and we support translation.
  const targetLang = locale === "vi" ? "vi" : "en";
  const sourceLang = jobLanguageCode === "mixed" ? "en" : jobLanguageCode;
  const needsTranslation =
    sourceLang !== targetLang &&
    sourceLang !== "unknown" &&
    (targetLang === "vi" || targetLang === "en");

  if (!needsTranslation) return null;

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
        "grid gap-3 rounded-[16px] border border-[var(--border-default)] bg-[var(--surface-secondary)] px-4 py-3 shadow-[0_8px_24px_rgba(11,34,57,0.06)] sm:grid-cols-[auto_minmax(0,1fr)_auto]",
        className,
      )}
      aria-live="polite"
    >
      {/* Icon */}
      <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-[var(--brand-primary)] shadow-[0_4px_12px_rgba(45,95,166,0.22)]">
        <Translate aria-hidden weight="duotone" className="size-3.5 text-white" />
      </span>

      {/* Label */}
      <p className="min-w-0 text-sm leading-6 text-[var(--text-secondary)]">
        {translated ? (
          <>
            <span className="font-semibold text-[var(--text-primary)]">
              {t("translatedLabel")}
            </span>{" "}
            <span className="text-[var(--text-muted)]">· {t("aiDisclaimer")}</span>
          </>
        ) : (
          <>
            {t("banner", {
              from: langLabel[sourceLang] ?? sourceLang,
              to: langLabel[targetLang] ?? targetLang,
            })}
          </>
        )}
      </p>

      {/* Error hint */}
      {error && (
        <p className="flex items-center gap-1 rounded-lg border border-[var(--red-100)] bg-[var(--red-50)] px-2 py-1 text-xs font-medium text-[var(--brand-red)] sm:col-start-2">
          <Warning aria-hidden weight="duotone" className="size-3.5" />
          {error === "unavailable" ? t("unavailable") : t("failed")}
        </p>
      )}

      {/* Action button */}
      {translated ? (
        <button
          type="button"
          onClick={handleRevert}
          className="flex shrink-0 items-center gap-1.5 rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-2 text-xs font-semibold text-[var(--text-secondary)] outline-none transition-colors hover:border-[var(--brand-primary)]/30 hover:text-[var(--brand-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
        >
          <ArrowCounterClockwise aria-hidden weight="duotone" className="size-3.5" />
          {t("viewOriginal")}
        </button>
      ) : (
        <button
          type="button"
          onClick={handleTranslate}
          disabled={loading}
          className={cn(
            "flex shrink-0 items-center gap-1.5 rounded-lg px-3.5 py-2 text-xs font-semibold outline-none transition-all focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30",
            loading
              ? "cursor-wait bg-[var(--blue-100)] text-[var(--brand-primary)]/55"
              : "bg-[var(--brand-primary)] text-white shadow-[0_6px_18px_rgba(45,95,166,0.24)] hover:bg-[var(--blue-700)]",
          )}
        >
          <Translate
            aria-hidden
            weight="duotone"
            className={cn("size-3.5", loading && "animate-spin")}
          />
          {loading ? t("translating") : t("translateBtn", { lang: langLabel[targetLang] })}
        </button>
      )}
    </div>
  );
}
