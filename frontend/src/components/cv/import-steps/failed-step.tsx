"use client";

import { useTranslations } from "next-intl";
import { FilePlus, UploadSimple, WarningCircle, WifiSlash } from "@phosphor-icons/react";
import { Button } from "@/components/ui";
import type { Ingestion } from "@/lib/api";

/** Step: failed / recovery. */
export function FailedStep({
  offline,
  fatalError,
  ingestion,
  tFail,
  onRetry,
  onAnother,
  onCreateFromTemplate,
}: {
  offline: boolean;
  fatalError: string | null;
  ingestion: Ingestion | null;
  tFail: ReturnType<typeof useTranslations>;
  onRetry: () => void;
  onAnother: () => void;
  onCreateFromTemplate: () => void;
}) {
  const t = useTranslations("cv.import");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");

  if (offline) {
    return (
      <div className="mx-auto max-w-lg">
        <div
          role="alert"
          className="flex items-start gap-3 rounded-xl bg-[var(--amber-100)] p-4"
        >
          <span className="flex size-7 shrink-0 items-center justify-center rounded-lg icon-chip-warning shadow-sm">
            <WifiSlash aria-hidden weight="duotone" className="size-4 text-white" />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {tStates("offlineTitle")}
            </p>
            <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
              {tStates("offlineBody")}
            </p>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button variant="primary" size="sm" onClick={onRetry}>
            {tc("retry")}
          </Button>
          <Button variant="secondary" size="sm" onClick={onAnother}>
            <UploadSimple aria-hidden weight="bold" className="size-4" />
            {t("uploadAnother")}
          </Button>
        </div>
      </div>
    );
  }

  const code = ingestion?.quality_code ?? null;
  const actions = ingestion?.next_actions ?? [];
  // Friendly title keyed by code; body uses the server's user-safe message.
  const titleKey = code ? `${code}.title` : null;
  const title =
    titleKey && tFail.has(titleKey) ? tFail(titleKey) : t("genericFailTitle");
  const body =
    ingestion?.quality_message ??
    fatalError ??
    t("genericFailBody");

  const showTemplate = actions.includes("create_from_template") || !actions.includes("upload_another");

  return (
    <div className="mx-auto max-w-lg">
      <div className="rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] backdrop-blur-md p-5 shadow-[var(--shadow-sm)]">
        <div className="flex items-start gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-xl icon-chip-warning shadow-sm">
            <WarningCircle aria-hidden weight="duotone" className="size-5 text-white" />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-bold text-[var(--text-primary)]">{title}</p>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">{body}</p>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" onClick={onAnother}>
            <UploadSimple aria-hidden weight="bold" className="size-4" />
            {t("uploadAnother")}
          </Button>
          {showTemplate && (
            <Button variant="ghost" size="sm" onClick={onCreateFromTemplate}>
              <FilePlus aria-hidden weight="bold" className="size-4" />
              {t("startFromTemplate")}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
