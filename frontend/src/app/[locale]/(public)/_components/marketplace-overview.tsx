"use client";

import { useId } from "react";
import Image from "next/image";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  Briefcase,
  Buildings,
  Star,
  Megaphone,
  CalendarCheck,
  WarningCircle,
  WifiSlash,
  ArrowRight,
  TrendUp,
  TrendDown,
  FileText,
  MapPin,
  Users,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import {
  Button,
  EmptyState,
  Skeleton,
  SponsoredLabel,
} from "@/components/ui";
import { JobRow } from "@/components/jobs/job-row";
import { EventCard } from "@/components/events/event-card";
import { CompanyAvatar } from "@/components/companies/company-avatar";
import { VerifiedBadge } from "@/components/ui/verified-badge";
import { RecommendationRail } from "@/components/discovery/recommendation-rail";
import { MarketplaceBannerCard } from "@/components/discovery/marketplace-banner-card";
import { TrackedItem } from "@/components/discovery/tracked-item";
import { companySignalTags, eventSignalTags } from "@/lib/discovery/signal-tags";
import { PopularRoles } from "@/components/discovery/popular-roles";
import { TrustModules } from "@/components/discovery/trust-modules";
import { DiscoveryPrivacyNote } from "@/components/discovery/discovery-privacy-note";
import { ApiError, marketplaceApi } from "@/lib/api";
import type { CompanySummary, EventSummary, JobsTrend, RecommendedEvent } from "@/lib/api";
import { cn } from "@/lib/utils";

export function MarketplaceOverview() {
  const t = useTranslations("marketplace");
  const tJobs = useTranslations("jobs");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const renderId = useId();

  const query = useQuery({
    queryKey: ["marketplace", "overview"],
    queryFn: () => marketplaceApi.overview(),
    retry: false,
  });

  if (query.isError) {
    const offline =
      query.error instanceof ApiError &&
      query.error.code === "NETWORK_ERROR";
    return (
      <Band>
        <EmptyState
          kind={offline ? "offline" : "error"}
          icon={offline ? WifiSlash : WarningCircle}
          title={tStates("errorTitle")}
          description={tStates("errorBody")}
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Button variant="secondary" onClick={() => query.refetch()}>
                {tc("retry")}
              </Button>
              <Link href="/jobs">
                <Button variant="ghost">{t("browseJobs")}</Button>
              </Link>
            </div>
          }
        />
      </Band>
    );
  }

  if (query.isPending) {
    return (
      <Band>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-[6.5rem] rounded-2xl" />
          ))}
        </div>
        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-[200px] rounded-2xl" />
          ))}
        </div>
      </Band>
    );
  }

  const data = query.data!;
  const {
    metrics,
    jobs_trend,
    sponsored_jobs,
    featured_jobs,
    recent_jobs,
    // Default to [] so a backend that predates the events slice never crashes
    // the gateway (the strip simply hides until the events arrays are present).
    sponsored_events = [],
    // Discovery rails (default-safe for a backend that predates this slice).
    hero_campaign = null,
    recommended_jobs = { source: "recent", personalized: false, items: [] },
    recommended_events = [],
    sponsored_banner = null,
    employer_spotlight = [],
    // Search chips + honest trust rail (spec §2/§6); default-safe for a
    // backend that predates this slice.
    popular_roles = [],
    trust_modules = [],
  } = data;

  const hasAnyInventory =
    (hero_campaign != null) ||
    recommended_jobs.items.length > 0 ||
    sponsored_jobs.length > 0 ||
    featured_jobs.length > 0 ||
    recent_jobs.length > 0 ||
    recommended_events.length > 0 ||
    sponsored_events.length > 0 ||
    employer_spotlight.length > 0 ||
    popular_roles.length > 0 ||
    trust_modules.length > 0;

  // Hide-if-null: scalar tiles depend only on `metrics`; the trend tile depends
  // only on a usable `jobs_trend` series. We never fabricate either.
  const metricItems = metrics
    ? ([
        { key: "active_jobs", value: metrics.active_jobs, icon: Briefcase },
        { key: "companies", value: metrics.companies, icon: Buildings },
        { key: "open_for_applications", value: metrics.open_for_applications, icon: FileText },
      ] as const)
    : [];

  const showTrendTile =
    jobs_trend !== null && jobs_trend.series.length >= 2;
  const tileCount = metricItems.length + (showTrendTile ? 1 : 0);
  const stripCols =
    tileCount >= 4
      ? "grid-cols-2 lg:grid-cols-4"
      : tileCount === 3
        ? "grid-cols-2 sm:grid-cols-3"
        : "grid-cols-2";

  return (
    <Band>
      {/* Live metric strip — each tile hides itself when its data is absent. */}
      {tileCount > 0 && (
        <dl className={cn("marketplace-card grid gap-0 overflow-hidden rounded-[16px]", stripCols)}>
          {metricItems.map((m) => {
            const Icon = m.icon;
            return (
            <div key={m.key} className={TILE_CLASS}>
              <span className="flex size-10 shrink-0 items-center justify-center rounded-full border border-[var(--border-default)] bg-[var(--surface-secondary)] text-[var(--brand-primary)]">
                <Icon aria-hidden weight="duotone" className="size-5" />
              </span>
              <span className="min-w-0">
                <dd className="text-2xl font-extrabold tabular-nums leading-none text-[var(--brand-primary)]">
                  {new Intl.NumberFormat().format(m.value)}
                </dd>
                <dt className="mt-1 text-sm text-[var(--text-secondary)]">
                  {t(`metric.${m.key}`)}
                </dt>
              </span>
            </div>
            );
          })}
          {showTrendTile && (
            <TrendTile
              trend={jobs_trend}
              label={t("metric.new_jobs_30d")}
              summary={t("trend.sparklineSummary", {
                value: new Intl.NumberFormat().format(jobs_trend.new_jobs_30d),
              })}
              deltaLabel={(pct) =>
                pct >= 0
                  ? t("trend.increaseLabel", { pct: pct.toFixed(1) })
                  : t("trend.decreaseLabel", { pct: Math.abs(pct).toFixed(1) })
              }
            />
          )}
        </dl>
      )}

      {!hasAnyInventory ? (
        <div className="mt-8">
          <EmptyState
            kind="empty"
            icon={Briefcase}
            title={t("emptyTitle")}
            description={t("emptyBody")}
            action={
              <div className="flex flex-wrap justify-center gap-2">
                <Link href="/companies">
                  <Button variant="secondary">{t("browseCompanies")}</Button>
                </Link>
                <Link href="/events">
                  <Button variant="ghost">{t("browseEvents")}</Button>
                </Link>
              </div>
            }
          />
        </div>
      ) : (
        <>
          {/* Hero campaign banner — live partner placement OR VinUni-curated
              fallback (editorial creative + polished class-keyed disclosure).
              Hidden when no campaign or fallback fills the slot. */}
          {hero_campaign && (
            <div className="mt-8">
              <MarketplaceBannerCard banner={hero_campaign} variant="hero" />
            </div>
          )}

          {/* Real role-family search chips (spec §2). Hidden when empty. */}
          {popular_roles.length > 0 && (
            <div className="mt-6">
              <PopularRoles roles={popular_roles} />
            </div>
          )}

          <div className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
            {/* Main column: recommended → sponsored → featured → recent. */}
            <div className="min-w-0">
              {/* Personalized OR honestly-labelled (recent/popular) rail. */}
              <RecommendationRail
                data={recommended_jobs}
                base="homepage"
                viewAllHref="/jobs"
                layout="dense"
              />

              {/* Honest privacy affordance for the guest discovery session —
                  placed right under the personalized rail it governs. */}
              {recommended_jobs.personalized && (
                <div className="mt-3">
                  <DiscoveryPrivacyNote />
                </div>
              )}

              {/* Flag-based sponsored inventory — labelled; hidden when empty. */}
              {sponsored_jobs.length > 0 && (
                <Section
                  className="mt-6"
                  icon={Megaphone}
                  iconGradient="icon-chip-warning"
                  title={t("featuredTitle")}
                  badge={<SponsoredLabel label={tJobs("sponsored")} />}
                >
                  <ul className="career-list-surface divide-y divide-[var(--border-default)]">
                    {sponsored_jobs.map((job) => (
                      <li key={job.id}>
                        <JobRow job={job} density="compact" />
                      </li>
                    ))}
                  </ul>
                </Section>
              )}

              {/* Featured employers/jobs. */}
              {featured_jobs.length > 0 && (
                <Section
                  className="mt-6"
                  icon={Star}
                  iconGradient="icon-chip-primary"
                  title={t("featuredTitle")}
                  action={<ViewAll href="/jobs" label={t("viewAllJobs")} />}
                >
                  <ul className="career-list-surface divide-y divide-[var(--border-default)]">
                    {featured_jobs.map((job) => (
                      <li key={job.id}>
                        <JobRow job={job} density="compact" />
                      </li>
                    ))}
                  </ul>
                </Section>
              )}

              {/* Recent jobs list. */}
              {recent_jobs.length > 0 && (
                <Section
                  className="mt-6"
                  icon={Briefcase}
                  iconGradient="icon-chip-success"
                  title={t("recentTitle")}
                  action={<ViewAll href="/jobs" label={t("viewAllJobs")} />}
                >
                  <ul className="career-list-surface divide-y divide-[var(--border-default)]">
                    {recent_jobs.map((job) => (
                      <li key={job.id}>
                        <JobRow job={job} density="compact" />
                      </li>
                    ))}
                  </ul>
                </Section>
              )}
            </div>

            {/* Right rail: curated employer/event/media modules, not a loose card dump. */}
            <aside className="flex flex-col gap-4 lg:sticky lg:top-24 lg:self-start">
              {employer_spotlight.length > 0 && (
                <EmployerSpotlightPanel
                  title={t("spotlightTitle")}
                  viewAllLabel={t("viewAllCompanies")}
                  renderId={renderId}
                  companies={employer_spotlight.slice(0, 4)}
                />
              )}

              <EventSpotlightPanel
                title={t("eventsTitle")}
                body={t("eventsTeaserBody")}
                viewAllLabel={t("viewAllEvents")}
                event={recommended_events[0] ?? sponsored_events[0] ?? null}
                renderId={renderId}
              />

              {sponsored_banner && (
                <MarketplaceBannerCard banner={sponsored_banner} variant="rail" />
              )}
            </aside>
          </div>

          {/* Sponsored events — labelled; hidden when there is no campaign. */}
          {sponsored_events.length > 0 && (
            <Section
              className="mt-10"
              icon={Megaphone}
              iconGradient="icon-chip-warning"
              title={t("sponsoredEventsTitle")}
              badge={<SponsoredLabel label={tJobs("sponsored")} />}
            >
              <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {sponsored_events.map((event) => (
                  <li key={event.id}>
                    <EventCard event={event} />
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {/* Upcoming events (honest "recent" source). Tracked for analytics. */}
          {recommended_events.length > 0 && (
            <Section
              className="mt-10"
              icon={CalendarCheck}
              iconGradient="icon-chip-success"
              title={t("eventsTitle")}
              action={<ViewAll href="/events" label={t("viewAllEvents")} />}
            >
              <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {recommended_events.map((event) => (
                  <li key={event.id}>
                    <TrackedItem
                      surface="homepage_recent"
                      targetType="event"
                      targetId={event.id}
                      renderId={renderId}
                      clickEvent="click"
                      signalTags={eventSignalTags(event)}
                    >
                      <EventCard event={event} />
                    </TrackedItem>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {/* Static, honest trust rail (spec §6) — closing reassurance strip. */}
          {trust_modules.length > 0 && (
            <div className="mt-10">
              <TrustModules modules={trust_modules} />
            </div>
          )}
        </>
      )}
    </Band>
  );
}

function EmployerSpotlightPanel({
  title,
  viewAllLabel,
  companies,
  renderId,
}: {
  title: string;
  viewAllLabel: string;
  companies: CompanySummary[];
  renderId: string;
}) {
  const tc = useTranslations("companies");
  return (
    <section
      aria-labelledby={`${renderId}-spotlight`}
      className="marketplace-card overflow-hidden rounded-[18px]"
    >
      <div className="flex items-center justify-between gap-3 border-b border-[var(--border-default)] px-4 py-3">
        <h2
          id={`${renderId}-spotlight`}
          className="flex items-center gap-2 text-base font-extrabold tracking-tight text-[var(--text-primary)]"
        >
          <span className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--gray-600)] to-[var(--brand-primary)] shadow-sm">
            <Buildings aria-hidden weight="duotone" className="size-4 text-white" />
          </span>
          {title}
        </h2>
        <ViewAll href="/companies" label={viewAllLabel} />
      </div>
      <ul className="divide-y divide-[var(--border-default)]">
        {companies.map((company) => (
          <li key={company.id}>
            <TrackedItem
              surface="employer_spotlight"
              targetType="company"
              targetId={company.id}
              renderId={renderId}
              signalTags={companySignalTags(company)}
            >
              <Link
                href={`/companies/${company.slug}`}
                className="group grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 px-4 py-3 outline-none transition-colors hover:bg-[var(--surface-secondary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
              >
                <CompanyAvatar
                  name={company.display_name}
                  logoUrl={company.logo_url}
                  size="sm"
                />
                <span className="min-w-0">
                  <span className="flex min-w-0 items-center gap-1.5">
                    <span className="truncate text-sm font-bold text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]">
                      {company.display_name}
                    </span>
                    {company.is_verified && (
                      <VerifiedBadge label={tc("verified")} className="[&_svg]:size-3.5" />
                    )}
                  </span>
                  <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-[var(--text-muted)]">
                    {company.industry && <span>{formatSnake(company.industry)}</span>}
                    {company.headquarters_city && (
                      <span className="inline-flex items-center gap-1">
                        <MapPin aria-hidden weight="duotone" className="size-3.5" />
                        {company.headquarters_city}
                      </span>
                    )}
                  </span>
                </span>
                <span className="inline-flex items-center gap-1 rounded-full border border-[var(--border-default)] bg-[var(--surface-secondary)] px-2 py-1 text-xs font-semibold text-[var(--text-secondary)]">
                  <Briefcase aria-hidden weight="duotone" className="size-3.5" />
                  {company.active_job_count}
                </span>
              </Link>
            </TrackedItem>
          </li>
        ))}
      </ul>
    </section>
  );
}

function EventSpotlightPanel({
  title,
  body,
  viewAllLabel,
  event,
  renderId,
}: {
  title: string;
  body: string;
  viewAllLabel: string;
  event: EventSummary | RecommendedEvent | null;
  renderId: string;
}) {
  const startsAt = event ? new Date(event.starts_at) : null;
  const dateLabel = startsAt
    ? new Intl.DateTimeFormat(undefined, {
        month: "short",
        day: "2-digit",
      }).format(startsAt)
    : null;
  const content = (
    <div className="marketplace-card overflow-hidden rounded-[18px]">
      <div className="relative h-32 overflow-hidden bg-[var(--brand-primary)]">
        <Image
          src="/images/career-day-2026.jpg"
          alt=""
          fill
          sizes="360px"
          className="object-cover"
          priority={false}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent" />
        {dateLabel && (
          <span className="absolute left-4 top-4 rounded-xl bg-[var(--surface-card)] px-3 py-2 text-center text-xs font-extrabold uppercase tracking-wide text-[var(--brand-primary)] shadow-sm">
            {dateLabel}
          </span>
        )}
      </div>
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-base font-extrabold tracking-tight text-[var(--text-primary)]">
            {event?.title ?? title}
          </h2>
          <CalendarCheck
            aria-hidden
            weight="duotone"
            className="size-5 shrink-0 text-[var(--brand-primary)]"
          />
        </div>
        <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
          {event
            ? [
                event.event_type_label,
                event.format_label,
                event.venue?.name ?? event.venue?.address ?? null,
              ]
                .filter(Boolean)
                .join(" · ")
            : body}
        </p>
        {event && (
          <p className="mt-2 inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--text-muted)]">
            <Users aria-hidden weight="duotone" className="size-3.5" />
            {event.registration_count}
          </p>
        )}
        <div className="mt-4">
          <ViewAll href={event ? `/events/${event.slug}` : "/events"} label={viewAllLabel} />
        </div>
      </div>
    </div>
  );

  if (!event) return content;

  return (
    <TrackedItem
      surface="homepage_recent"
      targetType="event"
      targetId={event.id}
      renderId={renderId}
      clickEvent="click"
      signalTags={eventSignalTags(event)}
    >
      {content}
    </TrackedItem>
  );
}

function formatSnake(value: string): string {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function ViewAll({ href, label }: { href: string; label: string }) {
  const td = useTranslations("discovery");
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-1 text-sm font-semibold text-[var(--brand-primary)] outline-none hover:underline focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
      aria-label={td("viewAllOf", { what: label })}
    >
      {label}
      <ArrowRight aria-hidden weight="bold" className="size-4" />
    </Link>
  );
}

/** Shared metric tile chrome. */
const TILE_CLASS =
  "flex min-h-[5.5rem] items-center gap-4 border-b border-r border-[var(--border-default)] px-6 py-4 last:border-r-0 lg:border-b-0";

function TrendTile({
  trend,
  label,
  summary,
  deltaLabel,
}: {
  trend: JobsTrend;
  label: string;
  summary: string;
  deltaLabel: (pct: number) => string;
}) {
  const counts = trend.series.map((p) => p.count);
  const pct = trend.delta_pct;
  const hasDelta = pct !== null;
  const positive = hasDelta && pct >= 0;
  const TrendIcon = positive ? TrendUp : TrendDown;

  return (
    <div className={TILE_CLASS}>
      <span className="flex size-10 shrink-0 items-center justify-center rounded-full border border-[var(--border-default)] bg-[var(--surface-secondary)] text-[var(--brand-primary)]">
        <TrendIcon aria-hidden weight="duotone" className="size-5" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <dd className="text-2xl font-extrabold tabular-nums leading-none text-[var(--brand-primary)]">
            {new Intl.NumberFormat().format(trend.new_jobs_30d)}
          </dd>
          {hasDelta && (
            <span
              aria-hidden
              className={cn(
                "inline-flex items-center gap-0.5 text-sm font-semibold tabular-nums",
                positive
                  ? "text-[var(--color-success)]"
                  : "text-[var(--color-error)]",
              )}
            >
              <TrendIcon weight="bold" className="size-4" />
              {Math.abs(pct).toFixed(1)}%
            </span>
          )}
        </div>
        <dt className="mt-1 text-sm text-[var(--text-secondary)]">{label}</dt>
      </div>
      <div className="hidden w-[112px] shrink-0 sm:block">
        <Sparkline values={counts} />
      </div>
      <span className="sr-only">
        {summary}
        {hasDelta ? ` ${deltaLabel(pct)}` : ""}
      </span>
    </div>
  );
}

function Sparkline({ values }: { values: number[] }) {
  const W = 120;
  const H = 32;
  const pad = 3;
  const n = values.length;
  const max = Math.max(...values);
  const min = Math.min(...values);
  const flat = max === min;

  const points = values.map((v, i) => {
    const x = n === 1 ? W / 2 : pad + (i / (n - 1)) * (W - pad * 2);
    const y = flat ? H / 2 : H - pad - ((v - min) / (max - min)) * (H - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const line = points.join(" ");
  const area = `${pad.toFixed(1)},${H} ${line} ${(W - pad).toFixed(1)},${H}`;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      className="h-8 w-full"
      aria-hidden
      focusable="false"
    >
      <polygon points={area} fill="var(--brand-primary)" fillOpacity={0.1} />
      <polyline
        points={line}
        fill="none"
        stroke="var(--brand-primary)"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

function Band({ children }: { children: React.ReactNode }) {
  return (
    <section className="mx-auto w-full max-w-[1400px] px-4 py-5 lg:px-6 lg:py-6">
      {children}
    </section>
  );
}

function Section({
  icon: Icon,
  iconGradient,
  title,
  badge,
  action,
  className,
  children,
}: {
  icon: React.ElementType;
  iconGradient?: string;
  title: string;
  badge?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={className}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2.5 text-xl font-bold tracking-tight text-[var(--text-primary)]">
          {iconGradient ? (
            <span className={cn("flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm", iconGradient)}>
              <Icon aria-hidden weight="duotone" className="size-4 text-white" />
            </span>
          ) : (
            <Icon aria-hidden weight="duotone" className="size-5 text-[var(--brand-primary)]" />
          )}
          {title}
          {badge}
        </h2>
        {action}
      </div>
      {children}
    </section>
  );
}
