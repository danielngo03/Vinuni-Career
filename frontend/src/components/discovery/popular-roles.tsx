"use client";

import { useTranslations } from "next-intl";
import { Compass } from "@phosphor-icons/react";
import { useRouter } from "@/i18n/navigation";
import type { PopularRole } from "@/lib/api";

/**
 * Real role-family chips (from genuine aggregate counts) that route to a search.
 * The family code is localized to BOTH a display label and a search term so the
 * resulting `/jobs?q=` query is meaningful. Hidden when there are no families.
 * Counts are real (never fabricated); we render the label, not a faked number.
 */
export function PopularRoles({ roles }: { roles: PopularRole[] }) {
  const t = useTranslations("discovery");
  const tf = useTranslations("discovery.roleFamily");
  const router = useRouter();

  if (!roles || roles.length === 0) return null;

  return (
    <section aria-labelledby="popular-roles-heading" className="mt-10">
      <h2
        id="popular-roles-heading"
        className="mb-3 flex items-center gap-2 text-base font-bold tracking-tight text-[var(--text-primary)]"
      >
        <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-success shadow-sm">
          <Compass aria-hidden weight="duotone" className="size-3.5 text-white" />
        </span>
        {t("popularRolesTitle")}
      </h2>
      <ul className="flex flex-wrap gap-2">
        {roles.map((role) => {
          const labelKey = `${role.role_family}.label`;
          const termKey = `${role.role_family}.term`;
          const label = tf.has(labelKey) ? tf(labelKey) : humanize(role.role_family);
          const term = tf.has(termKey) ? tf(termKey) : label;
          return (
            <li key={role.role_family}>
              <button
                type="button"
                onClick={() => router.push(`/jobs?q=${encodeURIComponent(term)}`)}
                className="inline-flex items-center gap-1.5 rounded-full border border-white/60 bg-white/75 px-3.5 py-1.5 text-sm font-medium text-[var(--text-secondary)] outline-none backdrop-blur-sm transition-all hover:border-[var(--brand-primary)]/60 hover:bg-white/90 hover:text-[var(--brand-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
              >
                {label}
                <span className="tabular-nums text-xs text-[var(--text-muted)]">
                  {role.job_count}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function humanize(family: string): string {
  return family
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
