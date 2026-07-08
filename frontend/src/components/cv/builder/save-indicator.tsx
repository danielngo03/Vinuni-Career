"use client";

import { useTranslations } from "next-intl";
import { ArrowsClockwise, CloudCheck, WarningCircle } from "@phosphor-icons/react";

export type SaveState = "idle" | "saving" | "saved" | "error";

export function SaveIndicator({ state }: { state: SaveState }) {
  const t = useTranslations("cv");

  return (
    <span
      role="status"
      aria-live="polite"
      className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)]"
    >
      {state === "saving" ? (
        <>
          <ArrowsClockwise
            aria-hidden
            weight="bold"
            className="size-3.5 animate-spin"
          />
          {t("builder.saving")}
        </>
      ) : state === "saved" ? (
        <>
          <CloudCheck
            aria-hidden
            weight="duotone"
            className="size-3.5 text-[var(--brand-teal)]"
          />
          {t("builder.saved")}
        </>
      ) : state === "error" ? (
        <>
          <WarningCircle
            aria-hidden
            weight="duotone"
            className="size-3.5 text-[var(--brand-red)]"
          />
          {t("builder.saveError")}
        </>
      ) : null}
    </span>
  );
}
