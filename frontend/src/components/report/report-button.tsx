"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Flag } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { ReportModal } from "./report-modal";
import type { ReportEntityType } from "@/lib/api";

export interface ReportButtonProps {
  entityType: ReportEntityType;
  entityId: string;
  entityLabel?: string;
  /** "link" for inline text-style triggers (company/job header), "icon" for compact icon-only triggers (message thread). */
  variant?: "link" | "icon";
  className?: string;
}

/** Small, reusable "Report" trigger + modal (ADR-0014 abuse/content-reports). */
export function ReportButton({
  entityType,
  entityId,
  entityLabel,
  variant = "link",
  className,
}: ReportButtonProps) {
  const t = useTranslations("report");
  const [open, setOpen] = useState(false);

  return (
    <>
      {variant === "icon" ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label={t("trigger")}
          title={t("trigger")}
          className={cn(
            "rounded-lg p-1.5 text-[var(--text-muted)] outline-none hover:bg-[var(--red-50)] hover:text-[var(--brand-red)] focus-visible:ring-2 focus-visible:ring-[var(--brand-red)]",
            className,
          )}
        >
          <Flag aria-hidden weight="duotone" className="size-4" />
        </button>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className={cn(
            "inline-flex items-center gap-1 text-sm font-semibold text-[var(--text-muted)] outline-none hover:text-[var(--brand-red)] focus-visible:ring-2 focus-visible:ring-[var(--brand-red)]/30",
            className,
          )}
        >
          <Flag aria-hidden weight="duotone" className="size-4" />
          {t("trigger")}
        </button>
      )}
      <ReportModal
        open={open}
        onClose={() => setOpen(false)}
        entityType={entityType}
        entityId={entityId}
        entityLabel={entityLabel}
      />
    </>
  );
}
