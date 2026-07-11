"use client";

import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import {
  Compass,
  ArrowUpRight,
  ArrowRight,
  Briefcase,
  Buildings,
  CalendarCheck,
  TrendUp,
  TrendDown,
  WarningCircle,
  WifiSlash,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, EmptyState, Skeleton } from "@/components/ui";
import { PopularRoles } from "@/components/discovery/popular-roles";
import { ApiError, searchApi, marketplaceApi } from "@/lib/api";
import type { IndustryLeaf, IndustryRoot } from "@/lib/api";

/** Localized display name for any industry node. */
function nodeName(node: IndustryLeaf, locale: string): string {
  return locale === "vi" ? node.name_vi : node.name_en;
}

/** A guest search deep-link for a field/sub-field (the job board reads `?q=`). */
function fieldHref(name: string): string {
  return `/jobs?q=${encodeURIComponent(name)}`;
}

/**
 * Public Career Explore — a real discovery surface (not a "coming soon"
 * placeholder). It browses the live industry taxonomy (`GET /industries`) and
 * enriches it with real aggregates from `GET /marketplace/overview`
 * (popular role families + 30-day hiring momentum). Every card deep-links a
 * guest into the live job board; nothing here is fabricated.
 */
export function CareerExploreScreen() {
  const t = useTranslations("careerExplore");
  const tm = useTranslations("marketplace");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();

  const industries = useQuery({
    queryKey: ["search", "industryTree"],
    queryFn: () => searchApi.industryTree(),
    retry: false,
    staleTime: 300_000,
  });
  // Shares the marketplace query key so the request is deduplicated with the
  // landing surfaces. Best-effort: its sections simply hide if it fails.
  const overview = useQuery({
    queryKey: ["marketplace", "overview"],
    queryFn: () => marketplaceApi.overview(),
    retry: false,
    staleTime: 60_000,
  });

  const roots: IndustryRoot[] = industries.data ?? [];
  const metrics = overview.data?.metrics ?? null;
  const popularRoles = overview.data?.popular_roles ?? [];
  const trend = overview.data?.jobs_trend ?? null;

  return (
    <div className="mx-auto w-full max-w-[1280px] px-4 py-10 lg:px-6 lg:py-12">
      {/* ── Header ── */}
      <header className="max-w-2xl">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-1 text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">
          <Compass aria-hidden weight="duotone" className="size-3.5" />
          {t("eyebrow")}
        </span>
        <h1 className="mt-4 text-2xl font-black tracking-tight text-[var(--text-primary)] sm:text-3xl">
          {t("title")}
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">
          {t("subtitle")}
        </p>

        {metrics && (metrics.active_jobs != null || metrics.companies != null) && (
          <dl className="mt-5 flex flex-wrap gap-2.5">
            {metrics.active_jobs != null && (
              <MetricChip value={metrics.active_jobs.toLocaleString(locale)} label={tm("metric.active_jobs")} />
            )}
            {metrics.companies != null && (
              <MetricChip value={metrics.companies.toLocaleString(locale)} label={tm("metric.companies")} />
            )}
          </dl>
        )}
      </header>

      {/* ── Browse by field (signature) ── */}
      <section aria-labelledby="explore-fields-heading" className="mt-10">
        <div className="mb-4">
          <h2
            id="explore-fields-heading"
            className="text-lg font-bold tracking-tight text-[var(--text-primary)]"
          >
            {t("browseByFieldTitle")}
          </h2>
          <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
            {t("browseByFieldSubtitle")}
          </p>
        </div>

        {industries.isError ? (
          <FieldError
            offline={industries.error instanceof ApiError && industries.error.code === "NETWORK_ERROR"}
            title={tStates("errorTitle")}
            body={tStates("errorBody")}
            retryLabel={tc("retry")}
            onRetry={() => industries.refetch()}
            browseLabel={t("nextJobsTitle")}
          />
        ) : industries.isPending ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-[128px] rounded-xl" />
            ))}
          </div>
        ) : roots.length === 0 ? (
          <EmptyState
            kind="empty"
            icon={Compass}
            title={t("emptyTitle")}
            description={t("emptyBody")}
            action={
              <Link href="/jobs">
                <Button variant="secondary">{t("nextJobsTitle")}</Button>
              </Link>
            }
          />
        ) : (
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {roots.map((root) => {
              const name = nodeName(root, locale);
              const branches = root.children ?? [];
              return (
                <li key={root.id}>
                  <Link
                    href={fieldHref(name)}
                    aria-label={t("viewFieldJobs", { field: name })}
                    className="group flex h-full flex-col rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] p-4 outline-none transition-colors hover:border-[var(--brand-primary)]/40 hover:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="text-[0.95rem] font-semibold leading-snug text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]">
                        {name}
                      </h3>
                      <ArrowUpRight
                        aria-hidden
                        weight="bold"
                        className="mt-0.5 size-4 shrink-0 text-[var(--text-muted)] transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-[var(--brand-primary)]"
                      />
                    </div>
                    {branches.length > 0 && (
                      <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-[var(--text-muted)]">
                        {branches.slice(0, 4).map((b) => nodeName(b, locale)).join(" · ")}
                      </p>
                    )}
                    <span className="mt-auto pt-3 text-xs font-medium text-[var(--text-secondary)] group-hover:text-[var(--brand-primary)]">
                      {t("browseRoles")}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* ── Trending role families (best-effort, real counts) ── */}
      {popularRoles.length > 0 && <PopularRoles roles={popularRoles} />}

      {/* ── 30-day hiring momentum (best-effort, real series) ── */}
      {trend && trend.new_jobs_30d > 0 && (
        <section aria-labelledby="momentum-heading" className="mt-10">
          <h2
            id="momentum-heading"
            className="mb-3 text-lg font-bold tracking-tight text-[var(--text-primary)]"
          >
            {t("momentumTitle")}
          </h2>
          <div className="flex flex-col gap-4 rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] p-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-black tabular-nums text-[var(--text-primary)]">
                  {trend.new_jobs_30d.toLocaleString(locale)}
                </span>
                <span className="text-sm text-[var(--text-secondary)]">
                  {t("momentumNewJobs")}
                </span>
              </div>
              {trend.delta_pct != null && (
                <span className="mt-1.5 inline-flex items-center gap-1 text-xs font-medium text-[var(--text-secondary)]">
                  {trend.delta_pct >= 0 ? (
                    <TrendUp aria-hidden weight="bold" className="size-3.5" />
                  ) : (
                    <TrendDown aria-hidden weight="bold" className="size-3.5" />
                  )}
                  {trend.delta_pct > 0
                    ? t("momentumUp", { percent: Math.abs(Math.round(trend.delta_pct)) })
                    : trend.delta_pct < 0
                      ? t("momentumDown", { percent: Math.abs(Math.round(trend.delta_pct)) })
                      : t("momentumFlat")}
                </span>
              )}
            </div>
            <Sparkline values={trend.series?.map((p) => p.count) ?? []} />
          </div>
        </section>
      )}

      {/* ── Keep exploring ── */}
      <section aria-labelledby="explore-more-heading" className="mt-10">
        <h2
          id="explore-more-heading"
          className="mb-3 text-lg font-bold tracking-tight text-[var(--text-primary)]"
        >
          {t("exploreMoreTitle")}
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <ExploreCard href="/jobs" icon={Briefcase} title={t("nextJobsTitle")} body={t("nextJobsBody")} />
          <ExploreCard href="/companies" icon={Buildings} title={t("nextCompaniesTitle")} body={t("nextCompaniesBody")} />
          <ExploreCard href="/events" icon={CalendarCheck} title={t("nextEventsTitle")} body={t("nextEventsBody")} />
        </div>
      </section>
    </div>
  );
}

function MetricChip({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex items-baseline gap-1.5 rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-1.5">
      <dd className="text-base font-black tabular-nums text-[var(--text-primary)]">{value}</dd>
      <dt className="text-xs font-medium text-[var(--text-secondary)]">{label}</dt>
    </div>
  );
}

function ExploreCard({
  href,
  icon: Icon,
  title,
  body,
}: {
  href: string;
  icon: typeof Briefcase;
  title: string;
  body: string;
}) {
  return (
    <Link
      href={href}
      className="group flex items-start gap-3.5 rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] p-4 outline-none transition-colors hover:border-[var(--brand-primary)]/40 hover:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
    >
      <span className="flex size-10 shrink-0 items-center justify-center rounded-xl icon-chip-primary shadow-sm">
        <Icon aria-hidden weight="duotone" className="size-5" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1 text-sm font-semibold text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]">
          {title}
          <ArrowRight
            aria-hidden
            weight="bold"
            className="size-3.5 opacity-0 transition-opacity group-hover:opacity-100"
          />
        </span>
        <span className="mt-0.5 block text-xs leading-relaxed text-[var(--text-secondary)]">
          {body}
        </span>
      </span>
    </Link>
  );
}

function FieldError({
  offline,
  title,
  body,
  retryLabel,
  onRetry,
  browseLabel,
}: {
  offline: boolean;
  title: string;
  body: string;
  retryLabel: string;
  onRetry: () => void;
  browseLabel: string;
}) {
  return (
    <EmptyState
      kind={offline ? "offline" : "error"}
      icon={offline ? WifiSlash : WarningCircle}
      title={title}
      description={body}
      action={
        <div className="flex flex-wrap justify-center gap-2">
          <Button variant="secondary" onClick={onRetry}>
            {retryLabel}
          </Button>
          <Link href="/jobs">
            <Button variant="ghost">{browseLabel}</Button>
          </Link>
        </div>
      }
    />
  );
}

/** Minimal monochrome sparkline for the 30-day hiring series. */
function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const w = 128;
  const h = 36;
  const max = Math.max(...values);
  const min = Math.min(...values);
  const range = max - min || 1;
  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = h - ((v - min) / range) * h;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg
      aria-hidden
      width={w}
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      className="shrink-0 text-[var(--text-primary)]"
      preserveAspectRatio="none"
    >
      <polyline
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
