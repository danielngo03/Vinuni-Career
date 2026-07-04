"use client";

import { useTranslations } from "next-intl";
import {
  Archive,
  ArrowUp,
  EnvelopeSimple,
  TrashSimple,
  Warning,
  type Icon,
} from "@phosphor-icons/react";
import { Button, Modal } from "@/components/ui";
import { cn } from "@/lib/utils";
import type { CvQuotaAction, CvQuotaInfo } from "@/lib/api";

/**
 * Active-CV limit-reached recovery dialog (docs/CV_STUDIO_SPEC.md §5,
 * docs/EDGE_CASES_FAILURE_MODES.md). Shown when a create/duplicate/import call
 * returns 409 `cv_quota_reached`. Shows the server-localized message as the
 * primary text and the recovery actions the backend offered:
 *  - archive_existing / delete_draft -> guide the user into the library where a
 *    real archive action frees a slot (no fake backend).
 *  - request_more_quota / upgrade   -> honest disabled "coming soon" rows.
 */

const ACTION_ORDER: CvQuotaAction[] = [
  "archive_existing",
  "delete_draft",
  "request_more_quota",
  "upgrade",
];

const ACTION_ICON: Record<CvQuotaAction, Icon> = {
  archive_existing: Archive,
  delete_draft: TrashSimple,
  request_more_quota: EnvelopeSimple,
  upgrade: ArrowUp,
};

const ACTION_GRADIENT: Record<CvQuotaAction, string> = {
  archive_existing: "from-[var(--gray-400)] to-[var(--gray-600)]",
  delete_draft: "from-[var(--red-500)] to-[var(--red-700)]",
  request_more_quota: "from-[var(--brand-primary)] to-[var(--gray-800)]",
  upgrade: "from-[var(--teal-500)] to-[var(--teal-700)]",
};

export function CvQuotaModal({
  open,
  info,
  onClose,
  onGoToLibrary,
}: {
  open: boolean;
  info: CvQuotaInfo | null;
  onClose: () => void;
  /** Close the dialog and bring the CV library (with its archive controls) into view. */
  onGoToLibrary: () => void;
}) {
  const t = useTranslations("cv.quota");
  const tc = useTranslations("common");

  if (!info) return null;

  const actions = ACTION_ORDER.filter((a) => info.actions.includes(a));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t("modalTitle")}
      size="md"
      closeLabel={tc("close")}
      footer={
        <Button variant="ghost" onClick={onClose}>
          {tc("close")}
        </Button>
      }
    >
      <div className="flex items-start gap-3 rounded-xl bg-[var(--amber-100)] p-4">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-lg icon-chip-warning shadow-sm">
          <Warning aria-hidden weight="duotone" className="size-4 text-white" />
        </span>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            {info.message}
          </p>
          {info.limit > 0 && (
            <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
              {t("modalCount", { current: info.current, limit: info.limit })}
            </p>
          )}
        </div>
      </div>

      {actions.length > 0 && (
        <>
          <p className="mt-5 mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("recoverTitle")}
          </p>
          <ul className="space-y-2.5">
            {actions.map((action) => {
              const Ico = ACTION_ICON[action];
              const guided =
                action === "archive_existing" || action === "delete_draft";
              return (
                <li
                  key={action}
                  className="flex items-start gap-3 rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] p-3.5 backdrop-blur-sm"
                >
                  <span className={cn("flex size-7 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br shadow-sm", ACTION_GRADIENT[action])}>
                    <Ico aria-hidden weight="duotone" className="size-4 text-white" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="flex flex-wrap items-center gap-1.5 text-sm font-semibold text-[var(--text-primary)]">
                      {t(`actions.${action}.title`)}
                      {!guided && (
                        <span className="rounded-full bg-[var(--gray-100)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--gray-500)]">
                          {tc("comingSoon")}
                        </span>
                      )}
                    </p>
                    <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                      {t(`actions.${action}.body`)}
                    </p>
                  </div>
                  {guided ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      className="shrink-0"
                      onClick={onGoToLibrary}
                    >
                      {t("goToLibrary")}
                    </Button>
                  ) : (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="shrink-0"
                      disabled
                      aria-disabled
                      title={tc("comingSoon")}
                    >
                      {tc("comingSoon")}
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        </>
      )}
    </Modal>
  );
}
