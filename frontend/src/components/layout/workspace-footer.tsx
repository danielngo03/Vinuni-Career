"use client";

import { useTranslations } from "next-intl";

/**
 * Minimal footer for the Partner/University operational shell (DESIGN.md
 * §6.1.1). Ops surfaces are dense work tools, not marketing pages — no link
 * columns, just a single-line copyright bar so the page content stays the
 * focus.
 */
export function WorkspaceFooter() {
  const t = useTranslations("footer");
  const year = new Date().getFullYear();

  return (
    <footer className="border-t border-[var(--border-default)] px-4 py-3 lg:px-6">
      <p className="text-xs text-[var(--text-muted)]">
        {t("workspaceCopyright", { year })}
      </p>
    </footer>
  );
}
