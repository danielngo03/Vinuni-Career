"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useInfiniteQuery } from "@tanstack/react-query";
import {
  CalendarCheck,
  LightbulbFilament,
  MagnifyingGlass,
  Sparkle,
  SlidersHorizontal,
  WarningCircle,
  WifiSlash,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import {
  Button,
  EmptyState,
  Input,
  Select,
  Sheet,
  Skeleton,
} from "@/components/ui";
import { EventCard } from "./event-card";
import {
  ApiError,
  eventsApi,
  EVENT_TYPES,
  EVENT_FORMATS,
  type EventSummary,
} from "@/lib/api";

const PAGE_LIMIT = 12;

/**
 * Public events board. Keyword + type + mode filters apply server-side via the
 * public listing contract and are reflected in the query key so results refetch
 * on change. The initial keyword is read from the URL (`?q=`). On mobile the
 * filters collapse into a sheet (mirrors the jobs board). Stable card grid with
 * loading/empty/error/offline states per UI_QUALITY_BAR.md. When no events are
 * published the board shows an honest empty state — never fabricated cards.
 */
export function PublicEventBoard() {
  const t = useTranslations("events");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const searchParams = useSearchParams();

  const initialQ = searchParams.get("q") ?? "";
  const initialType = searchParams.get("event_type") ?? "";
  const initialFormat = searchParams.get("format") ?? "";

  const [searchInput, setSearchInput] = useState(initialQ);
  const [search, setSearch] = useState(initialQ);
  const [eventType, setEventType] = useState(initialType);
  const [format, setFormat] = useState(initialFormat);
  const [filtersOpen, setFiltersOpen] = useState(false);

  // Debounce the keyword so we don't refetch on every keystroke.
  useEffect(() => {
    const id = window.setTimeout(() => setSearch(searchInput.trim()), 350);
    return () => window.clearTimeout(id);
  }, [searchInput]);

  const query = useInfiniteQuery({
    queryKey: ["events", "public", search, eventType, format],
    queryFn: ({ pageParam }) =>
      eventsApi.listPublic({
        cursor: pageParam,
        limit: PAGE_LIMIT,
        q: search || undefined,
        event_type: eventType || undefined,
        format: format || undefined,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.page.next_cursor,
    retry: false,
  });

  const events: EventSummary[] = useMemo(
    () => query.data?.pages.flatMap((p) => p.data) ?? [],
    [query.data],
  );
  const total = query.data?.pages[0]?.page.total;

  const typeOptions = [
    { value: "", label: t("filterAllTypes") },
    ...EVENT_TYPES.map((v) => ({ value: v, label: t(`enums.eventType.${v}`) })),
  ];
  const formatOptions = [
    { value: "", label: t("filterAllFormats") },
    ...EVENT_FORMATS.map((v) => ({ value: v, label: t(`enums.format.${v}`) })),
  ];

  const activeFilterCount = (eventType ? 1 : 0) + (format ? 1 : 0);
  const hasFilters = Boolean(search || eventType || format);

  function clearFilters() {
    setSearchInput("");
    setSearch("");
    setEventType("");
    setFormat("");
  }

  return (
    <div className="career-container py-8 lg:py-10">
      <header className="mb-6">
        <h1 className="text-[2rem] font-extrabold tracking-tight text-[var(--text-primary)]">
          {t("boardTitle")}
        </h1>
        <p className="mt-1 max-w-2xl text-sm leading-6 text-[var(--text-secondary)]">
          {t("boardSubtitle")}
        </p>
      </header>

      {/* Filter toolbar — chips on desktop, sheet on mobile. */}
      <div className="marketplace-panel mb-5 space-y-3 rounded-[16px] p-4">
        {/* Search row */}
        <div className="flex gap-3">
          <div className="relative flex-1">
            <MagnifyingGlass
              aria-hidden
              weight="duotone"
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-[var(--text-muted)]"
            />
            <Input
              type="search"
              aria-label={t("searchLabel")}
              placeholder={t("searchPlaceholder")}
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="pl-9"
            />
          </div>
          {/* Mobile: open filter sheet */}
          <Button
            variant="secondary"
            onClick={() => setFiltersOpen(true)}
            className="lg:hidden"
          >
            <SlidersHorizontal aria-hidden weight="bold" className="size-4" />
            {t("filters")}
            {activeFilterCount > 0 && (
              <span className="ml-1 inline-flex min-w-5 items-center justify-center rounded-full bg-[var(--brand-primary)] px-1.5 text-xs font-bold text-white">
                {activeFilterCount}
              </span>
            )}
          </Button>
          {/* Desktop: clear button */}
          <Button
            variant="ghost"
            onClick={clearFilters}
            disabled={!hasFilters}
            className="hidden lg:inline-flex"
          >
            {t("clearFilters")}
          </Button>
        </div>

        {/* Desktop: Event type chips */}
        <div className="hidden flex-wrap gap-2 lg:flex">
          {typeOptions.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setEventType(opt.value)}
              className={cn(
                "inline-flex shrink-0 items-center rounded-full px-3.5 py-1.5 text-xs font-semibold transition-all",
                eventType === opt.value
                  ? "bg-[var(--brand-primary)] text-white shadow-sm"
                  : "border border-[var(--border-default)] bg-[var(--surface-card)] text-[var(--text-secondary)] hover:border-[var(--border-strong)]",
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {/* Desktop: Format chips */}
        <div className="hidden flex-wrap gap-2 lg:flex">
          {formatOptions.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setFormat(opt.value)}
              className={cn(
                "inline-flex shrink-0 items-center rounded-full px-3.5 py-1.5 text-xs font-semibold transition-all",
                format === opt.value
                  ? "bg-[var(--brand-primary)] text-white shadow-sm"
                  : "border border-[var(--border-default)] bg-[var(--surface-card)] text-[var(--text-secondary)] hover:border-[var(--border-strong)]",
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <Sheet
        open={filtersOpen}
        onClose={() => setFiltersOpen(false)}
        title={t("filters")}
        closeLabel={tc("close")}
      >
        <div className="flex flex-col gap-4">
          <Select
            label={t("filterTypeLabel")}
            value={eventType}
            onChange={(e) => setEventType(e.target.value)}
            options={typeOptions}
          />
          <Select
            label={t("filterFormatLabel")}
            value={format}
            onChange={(e) => setFormat(e.target.value)}
            options={formatOptions}
          />
          <div className="mt-2 flex gap-2">
            <Button
              variant="ghost"
              onClick={clearFilters}
              disabled={!hasFilters}
              className="flex-1"
            >
              {t("clearFilters")}
            </Button>
            <Button
              variant="primary"
              onClick={() => setFiltersOpen(false)}
              className="flex-1"
            >
              {t("applyFilters")}
            </Button>
          </div>
        </div>
      </Sheet>

      {/* Result count (stable region) */}
      <p className="mb-4 text-sm text-[var(--text-secondary)]" role="status">
        {query.isPending
          ? tc("loading")
          : t("resultCount", { count: total ?? events.length })}
      </p>

      {query.isError ? (
        <EmptyState
          kind={
            query.error instanceof ApiError &&
            query.error.code === "NETWORK_ERROR"
              ? "offline"
              : "error"
          }
          icon={
            query.error instanceof ApiError &&
            query.error.code === "NETWORK_ERROR"
              ? WifiSlash
              : WarningCircle
          }
          title={tStates("errorTitle")}
          description={tStates("errorBody")}
          action={
            <Button variant="secondary" onClick={() => query.refetch()}>
              {tc("retry")}
            </Button>
          }
        />
      ) : query.isPending ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="marketplace-card overflow-hidden rounded-[14px]"
            >
              <Skeleton className="aspect-[16/9] w-full rounded-none" />
              <div className="p-4">
                <Skeleton className="h-5 w-3/4" />
                <Skeleton className="mt-3 h-4 w-1/2" />
                <Skeleton className="mt-2 h-4 w-2/5" />
              </div>
            </div>
          ))}
        </div>
      ) : events.length === 0 ? (
        <EmptyState
          kind="empty"
          icon={CalendarCheck}
          title={hasFilters ? t("noMatchTitle") : t("emptyTitle")}
          description={hasFilters ? t("noMatchBody") : t("emptyBody")}
          action={
            hasFilters ? (
              <Button variant="secondary" onClick={clearFilters}>
                {t("clearFilters")}
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          {/* AI Event Discovery Insights */}
          {events.length > 0 && !hasFilters && (() => {
            const now = Date.now();
            const soonCount = events.filter((e) => {
              const ms = new Date(e.starts_at).getTime() - now;
              return ms > 0 && ms <= 7 * 86_400_000;
            }).length;
            const limitedSeats = events.filter(
              (e) => e.seats_remaining !== null && e.seats_remaining < 10,
            ).length;
            const featuredCount = events.filter((e) => e.is_featured).length;
            const insights: string[] = [];
            if (soonCount > 0) insights.push(t("aiInsightSoon", { count: soonCount }));
            if (limitedSeats > 0) insights.push(t("aiInsightLimitedSeats", { count: limitedSeats }));
            if (featuredCount > 0) insights.push(t("aiInsightFeatured", { count: featuredCount }));
            if (insights.length === 0) return null;
            return (
              <div className={cn(
                "mb-6 rounded-[14px] border p-4",
                "border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-white",
              )}>
                <p className="mb-3 flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-info shadow-sm">
                    <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
                  </span>
                  {t("aiBoardInsightsTitle")}
                </p>
                <ul className="space-y-1.5">
                  {insights.map((s, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-[var(--text-secondary)]">
                      <LightbulbFilament aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0 text-[var(--ai-accent)]" />
                      {s}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })()}

          <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {events.map((event) => (
              <li key={event.id}>
                <EventCard event={event} />
              </li>
            ))}
          </ul>

          {query.hasNextPage && (
            <div className="mt-8 flex justify-center">
              <Button
                variant="secondary"
                loading={query.isFetchingNextPage}
                onClick={() => query.fetchNextPage()}
              >
                {tc("loadMore")}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
