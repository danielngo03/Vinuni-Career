"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useInfiniteQuery } from "@tanstack/react-query";
import { MapPin, ShieldCheck, Users, Clock, ArrowRight } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import {
  Card,
  EmptyState,
  FilterBar,
  StatusChip,
} from "@/components/kit";
import { formatRelativeTime } from "@/lib/format";
import { ApiError, talentPoolApi, type TalentCard } from "@/lib/api";

/* -------------------------------------------------------------------------- */
/* Masked identity avatar                                                      */
/* -------------------------------------------------------------------------- */

/**
 * Blind-screening avatar. For a masked candidate we never render a photo — a
 * neutral shielded monogram stands in for the withheld identity. For the
 * identified view (university staff), we still avoid loading remote photos here
 * and use a stable monogram to keep the grid calm.
 */
function MaskedAvatar({ handle }: { handle: string }) {
  const code = handle.replace(/^UV-/, "").slice(0, 2) || "UV";
  return (
    <span className="relative flex size-11 shrink-0 items-center justify-center rounded-full bg-[var(--viz-indigo-soft)] text-[var(--viz-indigo)]">
      <span className="type-small font-bold tabular-nums tracking-tight">{code}</span>
      <span className="absolute -bottom-0.5 -right-0.5 flex size-4 items-center justify-center rounded-full bg-card">
        <ShieldCheck className="size-3.5" strokeWidth={2} style={{ color: "var(--content-info)" }} />
      </span>
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* Talent card                                                                 */
/* -------------------------------------------------------------------------- */

function TalentPoolCard({ card, locale }: { card: TalentCard; locale: string }) {
  const t = useTranslations("talentPool");
  const location = [card.location_city, card.location_country].filter(Boolean).join(", ");
  const handle = card.anonymous_id ?? card.display_name;

  return (
    <Link
      href={`/partner/talent/${card.profile_id}`}
      className="group block rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
    >
      <Card interactive className="flex h-full flex-col p-4">
        <div className="flex items-start gap-3">
          <MaskedAvatar handle={handle} />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="type-h3 truncate font-semibold text-foreground group-hover:text-[var(--brand-primary)]">
                {handle}
              </span>
            </div>
            <p className="type-caption mt-0.5 text-muted-foreground">
              {card.identity_masked ? t("maskedLabel") : t("identifiedLabel")}
            </p>
          </div>
          <ArrowRight
            aria-hidden
            strokeWidth={2}
            className="mt-1 size-4 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
          />
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          {card.is_open_to_work && (
            <StatusChip tone="success" dot size="sm">
              {t("openToWork")}
            </StatusChip>
          )}
        </div>

        <dl className="mt-3 space-y-1.5 border-t border-border pt-3 text-[0.8125rem]">
          <div className="flex items-center gap-2 text-muted-foreground">
            <MapPin aria-hidden className="size-3.5 shrink-0" strokeWidth={1.8} />
            <span className="truncate text-foreground">{location || t("locationUnknown")}</span>
          </div>
          {card.updated_at && (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Clock aria-hidden className="size-3.5 shrink-0" strokeWidth={1.8} />
              <span>{t("activeAgo", { time: formatRelativeTime(card.updated_at, locale) })}</span>
            </div>
          )}
        </dl>
      </Card>
    </Link>
  );
}

/* -------------------------------------------------------------------------- */
/* Screen                                                                       */
/* -------------------------------------------------------------------------- */

/**
 * Talent Pool — the partner blind-screening surface. Passive open-to-work
 * candidates are shown anonymised (backend-masked `UV-xxxx` handle, no
 * name/photo) with only the coarse signals a recruiter may screen on: location,
 * open-to-work, and freshness. Career detail lives in CVs — recruiters engage
 * through the reason-gated outreach flow on the profile detail. Every state
 * (loading / empty / auth / error) degrades honestly and no data is fabricated.
 */
export function TalentPoolScreen() {
  const t = useTranslations("talentPool");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");
  const locale = useLocale();

  const [keyword, setKeyword] = React.useState("");
  const [committedKeyword, setCommittedKeyword] = React.useState("");

  function applyFilters() {
    setCommittedKeyword(keyword.trim());
  }

  const query = useInfiniteQuery({
    queryKey: ["talent-pool", committedKeyword],
    queryFn: ({ pageParam }) =>
      talentPoolApi.search({
        keyword: committedKeyword || undefined,
        cursor: pageParam ?? undefined,
        limit: 20,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.page.next_cursor,
    retry: false,
  });

  const allCards = query.data?.pages.flatMap((p) => p.items) ?? [];
  const anyMasked = allCards.some((c) => c.identity_masked);

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />

      {/* Toolbar — keyword search matches coarse location only (identity-only model). */}
      <form
        className="mb-4"
        onSubmit={(e) => {
          e.preventDefault();
          applyFilters();
        }}
      >
        <FilterBar
          search={{
            value: keyword,
            onChange: setKeyword,
            placeholder: t("searchByLocation"),
            ariaLabel: t("searchByLocation"),
          }}
          actions={
            <Button type="submit" variant="primary" size="sm">
              <Users className="size-4" strokeWidth={1.8} />
              {t("search")}
            </Button>
          }
        />
      </form>

      {query.isPending ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-[168px] animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
          ))}
        </div>
      ) : query.isError ? (
        query.error instanceof ApiError && query.error.isAuthError ? (
          <EmptyState kind="auth" title={tStates("authTitle")} description={tStates("authBody")} />
        ) : query.error instanceof ApiError && query.error.isPermissionError ? (
          <EmptyState kind="permission" title={t("lockedTitle")} description={t("lockedBody")} />
        ) : (
          <EmptyState
            kind="error"
            title={tStates("errorTitle")}
            description={tStates("errorBody")}
            action={
              <Button variant="secondary" onClick={() => query.refetch()}>
                {tc("retry")}
              </Button>
            }
          />
        )
      ) : allCards.length === 0 ? (
        <EmptyState kind="empty" title={t("emptyTitle")} description={t("emptyBody")} />
      ) : (
        <div className="space-y-4">
          {/* Blind-screening disclosure — only when the caller sees masked cards. */}
          {anyMasked && (
            <div
              className="flex items-start gap-3 rounded-xl border border-border px-4 py-3"
              style={{ background: "var(--content-info-soft)" }}
            >
              <ShieldCheck
                aria-hidden
                className="mt-0.5 size-4 shrink-0"
                strokeWidth={1.9}
                style={{ color: "var(--content-info)" }}
              />
              <div className="min-w-0">
                <p className="text-[0.8125rem] font-semibold text-foreground">{t("blindTitle")}</p>
                <p className="type-caption mt-0.5 text-muted-foreground">{t("blindNote")}</p>
              </div>
            </div>
          )}

          <p className="type-small text-muted-foreground">
            {t("loadedCount", { count: allCards.length })}
          </p>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {allCards.map((card) => (
              <TalentPoolCard key={card.profile_id} card={card} locale={locale} />
            ))}
          </div>

          {query.hasNextPage && (
            <div className="flex justify-center pt-1">
              <Button
                variant="secondary"
                loading={query.isFetchingNextPage}
                onClick={() => void query.fetchNextPage()}
              >
                {tc("loadMore")}
              </Button>
            </div>
          )}
        </div>
      )}
    </>
  );
}
