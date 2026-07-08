"use client";

import { useTranslations } from "next-intl";
import {
  SealCheck,
  Lifebuoy,
  Buildings,
  ShieldCheck,
  Star,
} from "@phosphor-icons/react";
import type { TrustModule } from "@/lib/api";

/**
 * Trust rail (spec §2/§6). Static, honest reassurance content localized by
 * `key` — NO fabricated metrics or numbers are ever shown here. Unknown keys are
 * skipped. Hidden when the backend sends no modules.
 */
export function TrustModules({ modules }: { modules: TrustModule[] }) {
  const t = useTranslations("discovery.trust");
  const known = (modules ?? []).filter((m) => ICONS[m.key]);
  if (known.length === 0) return null;

  return (
    <section
      aria-labelledby="trust-heading"
      className="mt-10 border-t border-white/40 pt-8"
    >
      <h2 id="trust-heading" className="sr-only">
        {t("title")}
      </h2>
      <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {known.map((m) => {
          const Icon = ICONS[m.key] ?? ShieldCheck;
          return (
            <li
              key={m.key}
              className="marketplace-card flex items-start gap-3 rounded-[14px] p-4"
            >
              <span className="flex size-9 shrink-0 items-center justify-center rounded-lg icon-chip-success shadow-sm">
                <Icon aria-hidden weight="duotone" className="size-5 text-white" />
              </span>
              <div className="min-w-0">
                <h3 className="text-sm font-bold text-[var(--text-primary)]">
                  {t(`${m.key}.title`)}
                </h3>
                <p className="mt-0.5 text-xs leading-relaxed text-[var(--text-secondary)]">
                  {t(`${m.key}.body`)}
                </p>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

const ICONS: Record<string, React.ElementType> = {
  verified_by_vinuni: SealCheck,
  career_support: Lifebuoy,
  employer_quality: Buildings,
  data_privacy: ShieldCheck,
  student_success: Star,
};
