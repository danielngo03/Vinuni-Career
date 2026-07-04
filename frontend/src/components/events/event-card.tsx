"use client";

import { useLocale, useTranslations } from "next-intl";
import {
  CalendarBlank,
  Fire,
  MapPin,
  Tag,
  VideoCamera,
  Users,
  Star,
  SealCheck,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { StatusBadge, SponsoredLabel } from "@/components/ui";
import { useEventLabels } from "@/lib/events/labels";
import {
  EVENT_COVER_FALLBACK,
  formatEventDateShort,
  isEventFull,
} from "@/lib/events/format";
import type { EventSummary } from "@/lib/api";

function formatDayMonth(iso: string, locale: string): { day: string; month: string } {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return { day: "—", month: "" };
  const intlLocale = locale === "vi" ? "vi-VN" : "en-US";
  return {
    day: new Intl.DateTimeFormat(intlLocale, { day: "numeric" }).format(d),
    month: new Intl.DateTimeFormat(intlLocale, { month: "short" }).format(d),
  };
}

/**
 * Public event board card. Fixed structure for a stable grid (UI_QUALITY_BAR.md):
 * cover image with date stamp + type/mode pills + date/place + capacity + tags.
 */
export function EventCard({ event }: { event: EventSummary }) {
  const t = useTranslations("events");
  const locale = useLocale();
  const labels = useEventLabels();

  const online = event.format === "online";
  const cover = event.cover_image_url ?? EVENT_COVER_FALLBACK;
  const full = isEventFull(event);
  const where = online
    ? t("online")
    : (event.venue?.name ?? labels.format(event.format, event.format_label));

  const { day, month } = formatDayMonth(event.starts_at, locale);

  // Urgency: show fire badge when ≤10 seats remain and event is not yet full
  const urgentSeats =
    !full &&
    event.capacity !== null &&
    event.seats_remaining !== null &&
    event.seats_remaining <= 10 &&
    event.seats_remaining > 0;

  const visibleTags = event.tags?.slice(0, 2) ?? [];

  return (
    <Link
      href={`/events/${event.id}`}
      className="marketplace-card marketplace-card-hover group flex h-full flex-col overflow-hidden rounded-[14px] outline-none focus-visible:border-[var(--brand-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
    >
      {/* Cover */}
      <div className="relative aspect-[16/9] w-full overflow-hidden bg-[var(--bg-muted)]">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={cover}
          alt=""
          aria-hidden
          className="size-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
        />

        {/* Type + format pills — top-left */}
        <div className="absolute left-2 top-2 flex flex-wrap items-center gap-1.5">
          <span className="inline-flex items-center gap-1 rounded-full bg-[var(--surface-card)] px-2.5 py-0.5 text-xs font-semibold text-[var(--brand-primary)] shadow-[0_1px_4px_rgba(11,34,57,0.10)]">
            {labels.eventType(event.event_type, event.event_type_label)}
          </span>
          <span className="inline-flex items-center gap-1 rounded-full bg-[var(--surface-card)] px-2.5 py-0.5 text-xs font-medium text-[var(--text-secondary)] shadow-[0_1px_4px_rgba(11,34,57,0.10)]">
            {online ? (
              <VideoCamera aria-hidden weight="duotone" className="size-3.5" />
            ) : (
              <MapPin aria-hidden weight="duotone" className="size-3.5" />
            )}
            {labels.format(event.format, event.format_label)}
          </span>
        </div>

        {/* Sponsored/featured — top-right */}
        <div className="absolute right-2 top-2 flex flex-wrap items-center justify-end gap-1.5">
          {event.is_sponsored && <SponsoredLabel label={t("sponsored")} />}
          {event.is_featured && (
            <StatusBadge tone="featured">
              <Star aria-hidden weight="fill" className="size-3" />
              {t("featured")}
            </StatusBadge>
          )}
        </div>

        {/* Date stamp badge — bottom-left */}
        <div className="absolute bottom-2 left-2 flex flex-col items-center rounded-xl bg-[var(--surface-card)] px-2.5 py-1 text-center shadow-[0_2px_8px_rgba(11,34,57,0.15)]">
          <span className="text-lg font-extrabold leading-none text-[var(--brand-primary)]">
            {day}
          </span>
          <span className="mt-0.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-secondary)]">
            {month}
          </span>
        </div>

        {/* Urgency — bottom-right */}
        {urgentSeats && (
          <div className="absolute bottom-2 right-2">
            <span className="inline-flex items-center gap-1 rounded-full bg-[var(--red-600)]/90 px-2.5 py-1 text-xs font-semibold text-white shadow-[0_2px_8px_rgba(200,53,56,0.35)] backdrop-blur-sm">
              <Fire aria-hidden weight="fill" className="size-3.5" />
              {t("spotsLeft", { count: event.seats_remaining ?? 0 })}
            </span>
          </div>
        )}
        {full && (
          <div className="absolute bottom-2 right-2">
            <span className="inline-flex items-center rounded-full bg-[var(--text-primary)]/80 px-2.5 py-1 text-xs font-semibold text-white backdrop-blur-sm">
              {t("full")}
            </span>
          </div>
        )}
      </div>

      <div className="flex flex-1 flex-col p-4">
        <h3 className="line-clamp-2 text-base font-bold tracking-tight text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]">
          {event.title}
        </h3>

        {event.company && (
          <p className="mt-1 flex items-center gap-1 text-sm font-medium text-[var(--text-secondary)]">
            <span className="truncate">{event.company.display_name}</span>
            {event.company.is_verified && (
              <SealCheck
                aria-label={t("verified")}
                weight="fill"
                className="size-4 shrink-0 text-[var(--brand-teal)]"
              />
            )}
          </p>
        )}

        <dl className="mt-3 flex flex-1 flex-col gap-1.5 text-sm text-[var(--text-secondary)]">
          <div className="flex items-center gap-2">
            <CalendarBlank
              aria-hidden
              weight="duotone"
              className="size-4 shrink-0 text-[var(--text-muted)]"
            />
            <dt className="sr-only">{t("when")}</dt>
            <dd>{formatEventDateShort(event.starts_at, locale)}</dd>
          </div>
          <div className="flex items-center gap-2">
            {online ? (
              <VideoCamera
                aria-hidden
                weight="duotone"
                className="size-4 shrink-0 text-[var(--text-muted)]"
              />
            ) : (
              <MapPin
                aria-hidden
                weight="duotone"
                className="size-4 shrink-0 text-[var(--text-muted)]"
              />
            )}
            <dt className="sr-only">{t("where")}</dt>
            <dd className="truncate">{where}</dd>
          </div>
          {event.capacity !== null && !urgentSeats && !full && (
            <div className="flex items-center gap-2">
              <Users
                aria-hidden
                weight="duotone"
                className="size-4 shrink-0 text-[var(--text-muted)]"
              />
              <dt className="sr-only">{t("capacity")}</dt>
              <dd>{t("spotsLeft", { count: event.seats_remaining ?? 0 })}</dd>
            </div>
          )}
        </dl>

        {visibleTags.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-[var(--border-default)] pt-3">
            <Tag aria-hidden weight="duotone" className="size-3.5 shrink-0 text-[var(--text-muted)]" />
            {visibleTags.map((tag) => (
              <span
                key={tag}
                className="rounded-full border border-[var(--border-default)] bg-[var(--surface-secondary)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]"
              >
                {tag}
              </span>
            ))}
          </div>
        )}
      </div>
    </Link>
  );
}
