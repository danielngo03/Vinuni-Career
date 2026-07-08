"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Briefcase,
  Buildings,
  FileText,
  ArrowRight,
  CalendarBlank,
  MapPin,
} from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { marketplaceApi } from "@/lib/api";
import { Skeleton } from "@/components/ui";

/**
 * Right-sidebar bento cards — live metrics + first upcoming event.
 * Shares the same TanStack Query key as MarketplaceOverview so the request
 * is deduplicated (one network call serves both components).
 */
export function QuickSnapshotCard() {
  const t = useTranslations("marketplace");

  const { data, isPending } = useQuery({
    queryKey: ["marketplace", "overview"],
    queryFn: () => marketplaceApi.overview(),
    retry: false,
    staleTime: 60_000,
  });

  const metrics = data?.metrics ?? null;
  const event = data?.upcoming_events?.[0] ?? null;

  const stats = [
    {
      icon: Briefcase,
      gradient: "from-[var(--gray-700)] to-[var(--gray-900)]",
      label: t("metric.active_jobs"),
      value: metrics?.active_jobs ?? null,
      href: "/jobs",
    },
    {
      icon: Buildings,
      gradient: "from-[var(--teal-500)] to-[var(--teal-700)]",
      label: t("metric.companies"),
      value: metrics?.companies ?? null,
      href: "/companies",
    },
    {
      icon: FileText,
      gradient: "from-[var(--gray-600)] to-[var(--gray-800)]",
      label: t("metric.open_for_applications"),
      value: metrics?.open_for_applications ?? null,
      href: "/jobs",
    },
  ] as const;

  return (
    <div className="flex flex-col gap-4">
      {/* ── Metrics card ── */}
      <div className="rounded-[20px] border border-[var(--glass-border)] bg-[var(--glass-surface)] p-5 shadow-[0_4px_28px_rgba(11,34,57,0.10),0_1px_6px_rgba(11,34,57,0.05)] backdrop-blur-md">
        <p className="text-[10px] font-bold uppercase tracking-[0.13em] text-[var(--text-muted)]">
          {t("metricsTitle")}
        </p>
        <div className="mt-3 flex flex-col gap-1">
          {stats.map(({ icon: Icon, gradient, label, value, href }) => (
            <Link
              key={label}
              href={href}
              className="group flex items-center gap-3 rounded-xl px-2.5 py-2 outline-none transition-colors hover:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
            >
              <span className={`flex size-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br shadow-sm ${gradient}`}>
                <Icon aria-hidden weight="duotone" className="size-5 text-white" />
              </span>
              <div className="min-w-0 flex-1">
                {isPending ? (
                  <Skeleton className="mb-1 h-5 w-10" />
                ) : (
                  <span className="block text-[1.2rem] font-black leading-none text-[var(--brand-navy)]">
                    {value != null ? value.toLocaleString("vi-VN") : "—"}
                  </span>
                )}
                <span className="mt-0.5 block truncate text-[0.7rem] font-medium text-[var(--text-secondary)]">
                  {label}
                </span>
              </div>
              <ArrowRight
                aria-hidden
                weight="bold"
                className="size-3.5 shrink-0 text-[var(--text-muted)] opacity-0 transition-opacity group-hover:opacity-100"
              />
            </Link>
          ))}
        </div>
      </div>

      {/* ── Event preview card ── */}
      <div className="flex flex-1 flex-col rounded-[20px] bg-[var(--brand-navy)] p-5 shadow-[0_4px_24px_rgba(11,34,57,0.20)]">
        <p className="text-[10px] font-bold uppercase tracking-[0.13em] text-[var(--blue-300)]">
          {t("eventsTitle")}
        </p>

        {isPending ? (
          <div className="mt-3 space-y-2">
            <Skeleton className="h-5 w-4/5 bg-white/10" />
            <Skeleton className="h-3.5 w-1/2 bg-white/10" />
            <Skeleton className="mt-3 h-7 w-28 bg-white/10" />
          </div>
        ) : event ? (
          <>
            <h3 className="mt-3 text-[0.975rem] font-bold leading-snug text-white">
              {event.title}
            </h3>
            <div className="mt-2 flex flex-col gap-1">
              <span className="flex items-center gap-1.5 text-[0.7rem] font-medium text-[var(--blue-200)]">
                <CalendarBlank aria-hidden weight="bold" className="size-3.5 shrink-0" />
                {new Date(event.starts_at).toLocaleDateString("vi-VN", {
                  day: "numeric",
                  month: "long",
                  year: "numeric",
                })}
              </span>
              {event.venue?.name && (
                <span className="flex items-center gap-1.5 text-[0.7rem] font-medium text-[var(--blue-200)]">
                  <MapPin aria-hidden weight="bold" className="size-3.5 shrink-0" />
                  {event.venue.name}
                </span>
              )}
            </div>
            <Link
              href={`/events/${event.slug}`}
              className="mt-auto inline-flex w-fit items-center gap-1.5 rounded-xl bg-white/15 px-3.5 py-2 text-xs font-semibold text-white outline-none ring-1 ring-inset ring-white/20 transition-colors hover:bg-white/25 focus-visible:ring-2 focus-visible:ring-white/40"
            >
              {t("viewEvent")}
              <ArrowRight aria-hidden weight="bold" className="size-3.5" />
            </Link>
          </>
        ) : (
          <>
            <p className="mt-3 text-[0.95rem] font-bold leading-snug text-white">
              {t("eventsTeaserTitle")}
            </p>
            <p className="mt-1.5 text-[0.75rem] leading-relaxed text-[var(--blue-200)]">
              {t("eventsTeaserBody")}
            </p>
            <Link
              href="/events"
              className="mt-auto inline-flex w-fit items-center gap-1.5 rounded-xl bg-white/15 px-3.5 py-2 text-xs font-semibold text-white outline-none ring-1 ring-inset ring-white/20 transition-colors hover:bg-white/25 focus-visible:ring-2 focus-visible:ring-white/40"
            >
              {t("viewAllEvents")}
              <ArrowRight aria-hidden weight="bold" className="size-3.5" />
            </Link>
          </>
        )}
      </div>
    </div>
  );
}
