import { getTranslations } from "next-intl/server";
import {
  Compass,
  Briefcase,
  Buildings,
  ArrowRight,
} from "@phosphor-icons/react/dist/ssr";
import { Link } from "@/i18n/navigation";

/**
 * Career Explore (guides, skill paths, industry discovery) ships in a later
 * slice — there is no backend for it yet, so we never fake content. This is an
 * honest "coming soon" within the public gateway that still routes guests to
 * live surfaces (jobs, companies), mirroring the events placeholder pattern.
 */
export default async function CareerExplorePage() {
  const t = await getTranslations("careerExplore");

  const NEXT = [
    {
      href: "/jobs",
      icon: Briefcase,
      gradient: "icon-chip-success",
      title: t("nextJobsTitle"),
      body: t("nextJobsBody"),
    },
    {
      href: "/companies",
      icon: Buildings,
      gradient: "icon-chip-info",
      title: t("nextCompaniesTitle"),
      body: t("nextCompaniesBody"),
    },
  ] as const;

  return (
    <div className="mx-auto w-full max-w-[1280px] px-4 py-12 lg:px-6">
      <div className="rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] p-8 text-center backdrop-blur-md sm:p-12">
        <span className="mx-auto flex size-14 items-center justify-center rounded-2xl icon-chip-primary shadow-sm">
          <Compass aria-hidden weight="duotone" className="size-7 text-white" />
        </span>
        <h1 className="mt-5 text-2xl font-bold tracking-tight text-[var(--text-primary)] sm:text-3xl">
          {t("title")}
        </h1>
        <p className="mx-auto mt-2 max-w-xl text-sm leading-relaxed text-[var(--text-secondary)]">
          {t("comingSoonBody")}
        </p>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
        {NEXT.map(({ href, icon: Icon, gradient, title, body }) => (
          <Link
            key={href}
            href={href}
            className="group flex items-start gap-4 rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] p-6 outline-none backdrop-blur-md transition-colors hover:border-[var(--brand-primary)]/60 hover:bg-[var(--glass-surface-heavy)] focus-visible:border-[var(--brand-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
          >
            <span className={`flex size-11 shrink-0 items-center justify-center rounded-xl shadow-sm ${gradient}`}>
              <Icon aria-hidden weight="duotone" className="size-6 text-white" />
            </span>
            <span className="flex-1">
              <span className="flex items-center gap-1 text-base font-semibold text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]">
                {title}
                <ArrowRight
                  aria-hidden
                  weight="bold"
                  className="size-4 opacity-0 transition-opacity group-hover:opacity-100"
                />
              </span>
              <span className="mt-1 block text-sm text-[var(--text-secondary)]">
                {body}
              </span>
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}
