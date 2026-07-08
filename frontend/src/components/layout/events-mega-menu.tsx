"use client";

import { useId } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  Briefcase,
  CalendarBlank,
  CaretRight,
  GraduationCap,
  Sparkle,
  VideoCamera,
  type Icon,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Skeleton } from "@/components/ui";
import { VerifiedBadge } from "@/components/ui/verified-badge";
import { TrackedItem } from "@/components/discovery/tracked-item";
import { marketplaceApi } from "@/lib/api";
import type { EventFormat, EventSummary, EventType } from "@/lib/api";
import { EVENT_FORMATS, EVENT_TYPES } from "@/lib/api";
import { useEventLabels } from "@/lib/events/labels";
import { formatEventDateShort } from "@/lib/events/format";
import {
  FooterLink,
  MegaHeading,
  PublicMegaMenuFrame,
  InlineArrow,
  listLinkClass,
  pillLinkClass,
  spotlightCardClass,
  usePublicMegaMenuState,
} from "./public-mega-menu-frame";
import { MegaPromoCard, eventPromoFrom } from "./mega-campaign-card";

const EVENT_TYPE_ICONS: Record<string, Icon> = {
  career_fair: Briefcase,
  workshop: Sparkle,
  info_session: CalendarBlank,
  networking: GraduationCap,
  webinar: VideoCamera,
};

export function EventsMegaMenu({ isActive = false }: { isActive?: boolean }) {
  const t = useTranslations("eventMenu");
  const tNav = useTranslations("nav");
  const tCompanies = useTranslations("companies");
  const labels = useEventLabels();
  const locale = useLocale();
  const menu = usePublicMegaMenuState();

  const overviewQuery = useQuery({
    queryKey: ["marketplace", "overview"],
    queryFn: () => marketplaceApi.overview(),
    enabled: menu.hasOpened,
    retry: false,
    staleTime: 60_000,
  });

  const eventPool = [
    ...(overviewQuery.data?.recommended_events ?? []),
    ...(overviewQuery.data?.featured_events ?? []),
    ...(overviewQuery.data?.upcoming_events ?? []),
  ];
  const events = Array.from(new Map(eventPool.map((event) => [event.id, event])).values()).slice(0, 4);
  const spotlightEvent =
    overviewQuery.data?.sponsored_events?.[0] ??
    overviewQuery.data?.featured_events?.[0] ??
    events[0] ??
    null;
  const spotlightPromo = eventPromoFrom(
    spotlightEvent,
    spotlightEvent ? formatEventDateShort(spotlightEvent.starts_at, locale) : "",
  );

  return (
    <PublicMegaMenuFrame
      menu={menu}
      href="/events"
      label={tNav("events")}
      panelId="events-mega-menu"
      panelLabel={t("label")}
      isActive={isActive}
    >
      <div className="grid gap-x-6 gap-y-5 p-5 md:grid-cols-[1.15fr_0.92fr_0.95fr]">
        <section aria-labelledby="mega-events-upcoming">
          <MegaHeading id="mega-events-upcoming">{t("recommendedEvents")}</MegaHeading>
          <ul className="mt-3 flex flex-col gap-1">
            {overviewQuery.isPending && menu.hasOpened
              ? Array.from({ length: 4 }).map((_, i) => (
                  <li key={i} className="flex items-center gap-2.5 px-2 py-2">
                    <Skeleton className="size-10 rounded-xl" />
                    <div className="min-w-0 flex-1">
                      <Skeleton className="h-4 w-44" />
                      <Skeleton className="mt-1.5 h-3 w-28" />
                    </div>
                  </li>
                ))
              : events.length > 0
                ? events.map((event) => (
                    <EventMegaRow
                      key={event.id}
                      event={event}
                      locale={locale}
                      verifiedLabel={tCompanies("verified")}
                    />
                  ))
                : (
                  <li className="rounded-xl bg-[var(--surface-secondary)] px-3 py-3 text-sm text-[var(--text-muted)]">
                    {t("emptyEvents")}
                  </li>
                )}
          </ul>
          <FooterLink href="/events" label={t("viewAllEvents")} />
        </section>

        <section aria-labelledby="mega-events-types">
          <MegaHeading id="mega-events-types">{t("browseByType")}</MegaHeading>
          <ul className="mt-3 flex flex-col gap-0.5">
            {EVENT_TYPES.map((type: EventType) => {
              const TypeIcon = EVENT_TYPE_ICONS[type] ?? CalendarBlank;
              return (
                <li key={type}>
                  <Link
                    href={`/events?event_type=${encodeURIComponent(type)}`}
                    className={listLinkClass}
                  >
                    <TypeIcon aria-hidden weight="duotone" className="size-4 shrink-0 text-[var(--brand-primary)]" />
                    <span className="truncate">{labels.eventType(type)}</span>
                  </Link>
                </li>
              );
            })}
          </ul>

          <MegaHeading id="mega-events-format" className="mt-5">
            {t("browseByFormat")}
          </MegaHeading>
          <div className="mt-3 flex flex-wrap gap-2">
            {EVENT_FORMATS.map((format: EventFormat) => (
              <Link
                key={format}
                href={`/events?format=${encodeURIComponent(format)}`}
                className={pillLinkClass}
              >
                {labels.format(format)}
              </Link>
            ))}
          </div>
        </section>

        <section aria-labelledby="mega-events-spotlight">
          <MegaHeading id="mega-events-spotlight">{t("spotlight")}</MegaHeading>
          {spotlightPromo ? (
            <MegaPromoCard
              {...spotlightPromo}
              eyebrow={spotlightEvent?.is_sponsored ? t("sponsoredEvent") : t("spotlight")}
              surface="mega_events"
              targetType="event"
              renderId="mega-event-promo"
              className="mt-3"
            />
          ) : (
            <Link href="/events" className={spotlightCardClass}>
              <span className="flex size-10 items-center justify-center rounded-xl icon-chip-primary shadow-sm">
                <CalendarBlank aria-hidden weight="duotone" className="size-5 text-white" />
              </span>
              <span className="text-sm font-bold text-[var(--text-primary)]">
                {t("allEvents")}
              </span>
              <span className="text-sm text-[var(--text-secondary)]">
                {t("allEventsBlurb")}
              </span>
              <InlineArrow>{t("viewAllEvents")}</InlineArrow>
            </Link>
          )}
        </section>
      </div>
    </PublicMegaMenuFrame>
  );
}

function EventMegaRow({
  event,
  locale,
  verifiedLabel,
}: {
  event: EventSummary;
  locale: string;
  verifiedLabel: string;
}) {
  const labels = useEventLabels();
  const renderId = useId();
  return (
    <li>
      <TrackedItem
        surface="mega_events"
        targetType="event"
        targetId={event.id}
        renderId={`mega-event-${renderId}`}
        signalTags={{ event_ids: [event.id] }}
      >
        <Link
          href={`/events/${event.id}`}
          className="group flex items-start gap-2.5 rounded-xl px-2.5 py-2 outline-none transition-colors hover:bg-[var(--surface-secondary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
        >
          <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-[var(--surface-secondary)] text-[var(--brand-primary)]">
            <CalendarBlank aria-hidden weight="duotone" className="size-5" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-bold text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]">
              {event.title}
            </span>
            {event.company && (
              <span className="mt-0.5 flex min-w-0 items-center gap-1 text-xs font-medium text-[var(--text-secondary)]">
                <span className="truncate">{event.company.display_name}</span>
                {event.company.is_verified && (
                  <VerifiedBadge label={verifiedLabel} className="[&_svg]:size-3" />
                )}
              </span>
            )}
            <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-[var(--text-muted)]">
              <span>{labels.eventType(event.event_type, event.event_type_label)}</span>
              <span>{labels.format(event.format, event.format_label)}</span>
              <span>{formatEventDateShort(event.starts_at, locale)}</span>
            </span>
          </span>
          <CaretRight
            aria-hidden
            weight="bold"
            className="mt-1 size-3.5 shrink-0 text-[var(--text-muted)] opacity-0 transition-opacity group-hover:opacity-100"
          />
        </Link>
      </TrackedItem>
    </li>
  );
}
