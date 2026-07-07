"use client";

import { DownloadSimple } from "@phosphor-icons/react";
import { Button } from "./button";

export interface ExportButtonProps {
  onExport: () => void;
  /** Localized label, e.g. "Xuất CSV". */
  label: string;
  loading?: boolean;
  disabled?: boolean;
  /** Optional row count shown as "(N)" — helps confirm the export scope. */
  count?: number;
  size?: "sm" | "md";
}

/**
 * Standard export entrypoint for tables/lists. Thin wrapper over Button so the
 * ~7 hand-rolled export controls (audit log, logs explorer, candidates CSV…)
 * share one affordance, loading state, and disabled-when-empty behavior.
 */
export function ExportButton({
  onExport,
  label,
  loading = false,
  disabled = false,
  count,
  size = "sm",
}: ExportButtonProps) {
  return (
    <Button
      variant="secondary"
      size={size}
      onClick={onExport}
      loading={loading}
      disabled={disabled || count === 0}
    >
      <DownloadSimple aria-hidden weight="bold" className="size-4" />
      {label}
      {count != null && count > 0 ? ` (${count})` : ""}
    </Button>
  );
}
