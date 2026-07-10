"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Megaphone } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { DisclosureLabel } from "@/components/ui";
import { advertisingApi, type AllocationItem } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Sponsored-slot rail — renders the ALLOCATION ENGINE's `paid_sponsored` slots
 * for one public surface (spec §7.0) as a DISTINCT, clearly-separated rail.
 *
 * Hard rules enforced here:
 * - Every item carries the mandatory, NON-REMOVABLE paid disclosure
 *   (`item.disclosure.is_removable === false`); it is never stripped.
 * - Sponsored inventory is visually + structurally separated from organic /
 *   recommended / university-curated rails — it never masquerades as organic.
 * - A best-effort impression delivery event fires once when an item is shown,
 *   and a click event fires on navigation (privacy-safe; no PII/GPS).
 * - Renders NOTHING when the engine returns no filled sponsored slots (we never
 *   fabricate an ad).
 */
export function SponsoredSlotRail({
  surface,
  locations,
  majors,
  careers,
  workMode,
  className,
  layout = "grid",
}: {
  surface: string;
  locations?: string[];
  majors?: string[];
  careers?: string[];
  workMode?: string;
  className?: string;
  layout?: "grid" | "rail";
}) {
  const t = useTranslations("discovery.sponsored");
  const locale = useLocale();

  const query = useQuery({
    queryKey: ["advertising", "allocation", surface, locations, majors, careers, workMode, locale],
    queryFn: () =>
      advertisingApi.getAllocation({
        surface,
        locations,
        majors,
        careers,
        work_mode: workMode,
        locale,
      }),
    staleTime: 2 * 60 * 1000,
    retry: false,
  });

  // Flatten every filled paid position across the surface's slots.
  const items: AllocationItem[] = React.useMemo(() => {
    const slots = query.data?.slots ?? [];
    return slots.flatMap((s) => s.items ?? []);
  }, [query.data]);

  // Nothing to show → hide the rail entirely (never fabricate an ad).
  if (query.isError || items.length === 0) return null;

  return (
    <section
      aria-label={t("ariaLabel")}
      className={cn(
        "overflow-hidden rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)]",
        className,
      )}
    >
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-default)] px-4 py-3">
        <h2 className="flex items-center gap-2 text-sm font-bold tracking-tight text-[var(--text-primary)]">
          <span
            className="flex size-6 shrink-0 items-center justify-center rounded-md"
            style={{ background: "var(--content-warning-soft)", color: "var(--content-warning)" }}
          >
            <Megaphone aria-hidden className="size-3.5" strokeWidth={2} />
          </span>
          {t("title")}
        </h2>
        <p className="type-caption text-[var(--text-muted)]">{t("note")}</p>
      </header>
      <ul
        className={cn(
          "gap-3 p-4",
          layout === "grid" ? "grid grid-cols-1 sm:grid-cols-2" : "flex flex-col",
        )}
      >
        {items.map((item) => (
          <li key={`${item.campaign_id}:${item.slot_code}:${item.position}`}>
            <SponsoredItemCard item={item} viewLabel={t("viewLabel")} />
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Best-effort delivery-event write (privacy-safe; never breaks the surface). */
function fireEvent(item: AllocationItem, eventType: "impression" | "click") {
  advertisingApi
    .recordDeliveryEvent({
      campaign_id: item.campaign_id,
      slot_code: item.slot_code,
      event_type: eventType,
    })
    .catch(() => {
      /* best-effort — a delivery-event failure must never break serving */
    });
}

function itemHref(item: AllocationItem): string | null {
  if (item.creative?.click_target) return item.creative.click_target;
  if (item.target_id && item.target_type === "job") return `/jobs/${item.target_id}`;
  if (item.target_id && item.target_type === "event") return `/events/${item.target_id}`;
  return null;
}

function SponsoredItemCard({ item, viewLabel }: { item: AllocationItem; viewLabel: string }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const firedRef = React.useRef(false);

  // Fire a single impression when the card first enters the viewport.
  React.useEffect(() => {
    const node = ref.current;
    if (!node || firedRef.current) return;
    if (typeof IntersectionObserver === "undefined") {
      firedRef.current = true;
      fireEvent(item, "impression");
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting && !firedRef.current) {
            firedRef.current = true;
            fireEvent(item, "impression");
            observer.disconnect();
          }
        }
      },
      { threshold: 0.5 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [item]);

  const href = itemHref(item);
  const image = item.creative?.image_ref;
  const headline = item.creative?.headline ?? item.name;
  const body = item.creative?.body;
  const alt = item.creative?.alt ?? headline;

  const inner = (
    <div
      ref={ref}
      className="group flex h-full flex-col overflow-hidden rounded-xl border border-[var(--border-default)] bg-[var(--surface-secondary)] outline-none transition-colors hover:border-[var(--brand-primary)]/40 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
    >
      {image ? (
        <div className="relative">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={image} alt={alt ?? ""} loading="lazy" className="aspect-[16/9] w-full object-cover" />
          <span className="pointer-events-none absolute right-2 top-2 z-10">
            <DisclosureLabel disclosure={item.disclosure} />
          </span>
        </div>
      ) : (
        <div className="flex items-center justify-end px-3 pt-3">
          <DisclosureLabel disclosure={item.disclosure} />
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col p-3">
        <p className="line-clamp-2 font-bold tracking-tight text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]">
          {headline}
        </p>
        {body && <p className="mt-1 line-clamp-2 type-small text-[var(--text-secondary)]">{body}</p>}
        {href && (
          <span className="mt-auto inline-flex items-center gap-1 pt-2 text-sm font-semibold text-[var(--brand-primary)]">
            {viewLabel}
            <ArrowRight aria-hidden className="size-4" strokeWidth={2} />
          </span>
        )}
      </div>
    </div>
  );

  if (!href) return inner;

  return (
    <Link href={href} onClick={() => fireEvent(item, "click")} className="block h-full">
      {inner}
    </Link>
  );
}
