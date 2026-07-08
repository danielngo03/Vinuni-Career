"use client";

import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { CircleNotch, CheckCircle, WarningCircle } from "@phosphor-icons/react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Real backend health probe via the typed API client (GET /api/v1/health).
 * This is a genuine data surface with loading / online / offline states — not
 * a decorative widget. It never surfaces internal error details.
 */
export function PlatformStatus() {
  const t = useTranslations("landing");

  const { isPending, isError } = useQuery({
    queryKey: ["health"],
    queryFn: () => api.health(),
    retry: false,
    staleTime: 60_000,
  });

  const state = isPending ? "checking" : isError ? "offline" : "online";

  const config = {
    checking: {
      icon: CircleNotch,
      text: t("backendChecking"),
      tone: "text-[var(--text-muted)]",
      spin: true,
    },
    online: {
      icon: CheckCircle,
      text: t("backendOnline"),
      tone: "text-[var(--color-success)]",
      spin: false,
    },
    offline: {
      icon: WarningCircle,
      text: t("backendOffline"),
      tone: "text-[var(--color-warning)]",
      spin: false,
    },
  }[state];

  const Icon = config.icon;

  return (
    <div
      role="status"
      aria-live="polite"
      className="inline-flex items-center gap-2 rounded-full border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] px-3.5 py-1.5 text-sm shadow-[0_1px_8px_rgba(11,34,57,0.06)] backdrop-blur-sm"
    >
      <Icon
        aria-hidden
        weight="duotone"
        className={cn("size-4", config.tone, config.spin && "animate-spin")}
      />
      <span className="font-medium text-[var(--text-secondary)]">
        <span className="font-semibold text-[var(--text-primary)]">
          {t("platformStatus")}:
        </span>{" "}
        {config.text}
      </span>
    </div>
  );
}
