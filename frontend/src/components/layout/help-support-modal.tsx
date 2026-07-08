"use client";

import { useTranslations } from "next-intl";
import { Mail, MessageSquarePlus } from "lucide-react";
import { Button, Modal } from "@/components/ui";

const SUPPORT_EMAIL = "career@vinuni.edu.vn";

/**
 * Lightweight help/support panel for the workspace sidebar footer. Real,
 * static content only (a genuine institutional contact address + a bridge
 * into the feedback flow) — no fabricated FAQ/ticket system that isn't built.
 */
export function HelpSupportModal({
  open,
  onClose,
  onOpenFeedback,
}: {
  open: boolean;
  onClose: () => void;
  onOpenFeedback: () => void;
}) {
  const t = useTranslations("help");

  return (
    <Modal open={open} onClose={onClose} title={t("title")} description={t("subtitle")} size="sm">
      <div className="mt-4 space-y-3">
        <a
          href={`mailto:${SUPPORT_EMAIL}`}
          className="flex items-center gap-3 rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] p-3.5 outline-none transition-colors hover:border-[var(--brand-primary)]/40 hover:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
        >
          <span className="icon-chip-primary flex size-10 shrink-0 items-center justify-center rounded-[10px]">
            <Mail aria-hidden strokeWidth={1.8} className="size-[18px]" />
          </span>
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-[var(--text-primary)]">
              {t("contactLabel")}
            </span>
            <span className="block truncate text-sm text-[var(--brand-primary)]">
              {SUPPORT_EMAIL}
            </span>
            <span className="mt-0.5 block text-xs text-[var(--text-muted)]">
              {t("contactHint")}
            </span>
          </span>
        </a>

        <button
          type="button"
          onClick={() => {
            onClose();
            onOpenFeedback();
          }}
          className="flex w-full items-center gap-3 rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] p-3.5 text-left outline-none transition-colors hover:border-[var(--brand-primary)]/40 hover:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
        >
          <span className="icon-chip-success flex size-10 shrink-0 items-center justify-center rounded-[10px]">
            <MessageSquarePlus aria-hidden strokeWidth={1.8} className="size-[18px]" />
          </span>
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-[var(--text-primary)]">
              {t("feedbackPromptTitle")}
            </span>
            <span className="mt-0.5 block text-xs text-[var(--text-muted)]">
              {t("feedbackPromptBody")}
            </span>
          </span>
        </button>

        <div className="flex justify-end pt-1">
          <Button variant="ghost" onClick={onClose}>
            {t("close")}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
