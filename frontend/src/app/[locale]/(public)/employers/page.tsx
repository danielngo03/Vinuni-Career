import { getTranslations } from "next-intl/server";
import {
  Megaphone,
  UsersThree,
  Target,
  SealCheck,
  ArrowRight,
} from "@phosphor-icons/react/dist/ssr";
import { Link } from "@/i18n/navigation";
import { EmployerEntryActions } from "@/components/organization/employer-entry-actions";

/**
 * Employer acquisition landing (SCREEN_SPECS §1.1 "Employers"). Real conversion
 * surface — value proposition + primary CTA into partner registration. No fake
 * metrics or logos; copy is the source of truth (DESIGN.md §6.3). Reuses the
 * partner value framing already established in the landing namespace.
 */
export default async function EmployersPage() {
  const t = await getTranslations("employers");

  const BENEFITS = [
    { icon: Target, gradient: "icon-chip-primary", title: t("benefit1Title"), body: t("benefit1Body") },
    { icon: UsersThree, gradient: "icon-chip-success", title: t("benefit2Title"), body: t("benefit2Body") },
    { icon: Megaphone, gradient: "icon-chip-warning", title: t("benefit3Title"), body: t("benefit3Body") },
    { icon: SealCheck, gradient: "icon-chip-success", title: t("benefit4Title"), body: t("benefit4Body") },
  ] as const;

  return (
    <div>
      {/* Hero band — VinUni navy, consistent with the gateway identity. */}
      <section className="bg-[var(--bg-hero)] text-white">
        <div className="mx-auto max-w-[1280px] px-4 py-14 lg:px-6 lg:py-20">
          <div className="max-w-2xl">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-[var(--blue-200)]">
              <Megaphone aria-hidden weight="duotone" className="size-3.5" />
              {t("eyebrow")}
            </span>
            <h1 className="mt-4 text-3xl font-black leading-tight tracking-tight sm:text-4xl">
              {t("title")}
            </h1>
            <p className="mt-3 text-base font-medium text-[var(--blue-200)]">
              {t("subtitle")}
            </p>
            <div className="mt-7 flex flex-col gap-3 sm:flex-row">
              <EmployerEntryActions />
            </div>
          </div>
        </div>
      </section>

      {/* Value proposition grid. */}
      <section className="mx-auto max-w-[1280px] px-4 py-12 lg:px-6 lg:py-16">
        <h2 className="text-xl font-bold tracking-tight text-[var(--text-primary)]">
          {t("benefitsTitle")}
        </h2>
        <div className="mt-6 grid grid-cols-1 gap-5 sm:grid-cols-2">
          {BENEFITS.map(({ icon: Icon, gradient, title, body }) => (
            <div
              key={title}
              className="flex items-start gap-4 rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] p-6 shadow-[0_2px_12px_rgba(11,34,57,0.06)] backdrop-blur-md"
            >
              <span className={`flex size-11 shrink-0 items-center justify-center rounded-xl shadow-sm ${gradient}`}>
                <Icon aria-hidden weight="duotone" className="size-6 text-white" />
              </span>
              <div>
                <h3 className="text-base font-semibold text-[var(--text-primary)]">
                  {title}
                </h3>
                <p className="mt-1 text-sm leading-relaxed text-[var(--text-secondary)]">
                  {body}
                </p>
              </div>
            </div>
          ))}
        </div>

        {/* Closing CTA. */}
        <div className="mt-8 flex flex-col items-start gap-4 rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] p-6 backdrop-blur-sm sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="text-base font-bold text-[var(--text-primary)]">
              {t("closingTitle")}
            </h3>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              {t("closingBody")}
            </p>
          </div>
          <Link
            href="/auth/partner-registration"
            className="inline-flex h-11 shrink-0 items-center justify-center gap-1.5 rounded-lg bg-[var(--brand-primary)] px-6 text-sm font-semibold text-white shadow-[var(--shadow-brand)] outline-none transition-colors hover:bg-[var(--blue-700)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
          >
            {t("ctaRegister")}
            <ArrowRight aria-hidden weight="bold" className="size-4" />
          </Link>
        </div>
      </section>
    </div>
  );
}
