"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Handshake,
  Sparkle,
  Scales,
  Info,
  WarningCircle,
  Buildings,
  CalendarX,
  Lightbulb,
} from "@phosphor-icons/react";
import { Sheet, Button, StatusBadge } from "@/components/ui";
import { AiEnergyHint } from "@/components/jobs/ai-energy-hint";
import {
  applicationsApi,
  type OfferCompareRow,
  type OfferNegotiationResult,
} from "@/lib/api";
import { marketPositionTone, type MarketTone } from "@/lib/offers/negotiation";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const MARKET_TONE_CLASS: Record<MarketTone, string> = {
  below: "border-[var(--amber-100)] bg-[var(--amber-50)] text-[var(--amber-700)]",
  within: "border-[var(--border-default)] bg-[var(--surface-secondary)] text-[var(--text-secondary)]",
  above: "border-[var(--teal-100)] bg-[var(--teal-50)] text-[var(--teal-700)]",
  unknown: "border-[var(--border-default)] bg-[var(--surface-secondary)] text-[var(--text-muted)]",
};

/**
 * Student offer comparison + confirmation-gated AI negotiation guidance (WS-15).
 *
 * Deterministic side-by-side is FREE (`GET /offers/compare`); it renders the
 * student's OWN offers with their own (disclosed) comp, response deadline,
 * status, and the internal salary benchmark band + market-position verdict. The
 * AI negotiation narrative is on-demand, energy-metered, and CONFIRMATION-GATED:
 * the metered call fires ONLY after the student explicitly confirms in the
 * drawer. The `disclaimer` (server-localized) is ALWAYS shown — the product
 * never implies a guaranteed outcome. Renders nothing when the student has no
 * student-visible offers.
 */
export function OfferComparePanel() {
  const t = useTranslations("applications.offerCompare");
  const locale = useLocale();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const compare = useQuery({
    queryKey: ["offers", "compare"],
    queryFn: () => applicationsApi.compareOffers(),
    retry: false,
    staleTime: 60_000,
  });

  // Nothing to show until we know there is at least one offer (no skeleton flash
  // on a surface where offers are the exception, not the rule).
  if (compare.isPending || compare.isError) return null;
  const data = compare.data;
  if (!data || data.count === 0) return null;

  return (
    <section
      aria-label={t("title")}
      className="marketplace-card mb-5 overflow-hidden rounded-[12px]"
    >
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--border-default)] p-4">
        <div className="flex items-start gap-2.5">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-xl icon-chip-info">
            <Scales aria-hidden weight="duotone" className="size-5" />
          </span>
          <div className="min-w-0">
            <h2 className="text-base font-bold tracking-tight text-[var(--text-primary)]">
              {t("title")}
            </h2>
            <p className="mt-0.5 text-xs leading-relaxed text-[var(--text-muted)]">
              {t("subtitle")}
            </p>
          </div>
        </div>
        <Button variant="secondary" size="sm" onClick={() => setDrawerOpen(true)}>
          <Sparkle aria-hidden weight="fill" className="size-4" />
          {t("negotiateCta")}
        </Button>
      </header>

      <div className="p-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {data.offers.map((offer) => (
            <OfferCard key={offer.id} offer={offer} locale={locale} t={t} />
          ))}
        </div>
        {!data.comparable && (
          <p className="mt-3 flex items-start gap-1.5 text-xs text-[var(--text-muted)]">
            <Info aria-hidden weight="duotone" className="mt-0.5 size-3.5 shrink-0" />
            {t("singleOfferNote")}
          </p>
        )}
      </div>

      <NegotiationDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        t={t}
      />
    </section>
  );
}

function OfferCard({
  offer,
  locale,
  t,
}: {
  offer: OfferCompareRow;
  locale: string;
  t: ReturnType<typeof useTranslations<"applications.offerCompare">>;
}) {
  const tone = marketPositionTone(offer.benchmark);
  return (
    <div className="rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] p-3.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-bold text-[var(--text-primary)]" title={offer.position_title}>
            {offer.position_title}
          </p>
          {offer.company_name && (
            <p className="mt-0.5 flex items-center gap-1 truncate text-xs text-[var(--text-secondary)]">
              <Buildings aria-hidden weight="duotone" className="size-3.5 shrink-0 text-[var(--text-muted)]" />
              {offer.company_name}
            </p>
          )}
        </div>
        <StatusBadge tone="info" className="shrink-0 text-[10px]">
          {offer.status_label}
        </StatusBadge>
      </div>

      <dl className="mt-3 space-y-1.5 text-xs">
        <div className="flex items-center justify-between gap-2">
          <dt className="text-[var(--text-muted)]">{t("compCol")}</dt>
          <dd
            className={cn(
              "font-semibold tabular-nums",
              offer.comp_summary ? "text-[var(--text-primary)]" : "text-[var(--text-muted)]",
            )}
          >
            {offer.comp_summary ?? t("compUndisclosed")}
          </dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className="flex items-center gap-1 text-[var(--text-muted)]">
            <CalendarX aria-hidden weight="duotone" className="size-3.5" />
            {t("deadlineCol")}
          </dt>
          <dd className="font-medium text-[var(--text-secondary)]">
            {formatDateTime(offer.expiry_date, locale)}
          </dd>
        </div>
      </dl>

      {/* Internal salary benchmark band + market-position verdict (advisory). */}
      <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-[var(--border-default)] pt-3">
        {offer.benchmark.found && offer.benchmark.market_band ? (
          <>
            <span className="rounded-full bg-[var(--bg-subtle)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]">
              {t("marketBand", { band: offer.benchmark.market_band })}
            </span>
            {offer.benchmark.position_vs_market && (
              <span className={cn("rounded-full border px-2 py-0.5 text-[10px] font-semibold", MARKET_TONE_CLASS[tone])}>
                {t(`position.${offer.benchmark.position_vs_market}`)}
              </span>
            )}
          </>
        ) : (
          <span className="text-[10px] font-medium text-[var(--text-muted)]">
            {t("marketUnknown")}
          </span>
        )}
      </div>
    </div>
  );
}

/**
 * Confirmation-gated negotiation drawer. Opening it shows the energy cost + a
 * confirm step; the metered `POST /offers/negotiation-guidance {confirm:true}`
 * fires ONLY from the confirm button (never on open). The disclaimer is always
 * shown once a result is back.
 */
function NegotiationDrawer({
  open,
  onClose,
  t,
}: {
  open: boolean;
  onClose: () => void;
  t: ReturnType<typeof useTranslations<"applications.offerCompare">>;
}) {
  const [result, setResult] = useState<OfferNegotiationResult | null>(null);

  const run = useMutation({
    // Explicit user consent — `confirm: true` is sent ONLY here, from the
    // confirm button's onClick, so nothing is fetched before confirmation.
    mutationFn: () => applicationsApi.negotiationGuidance(true),
    onSuccess: (res) => setResult(res),
  });

  function handleClose() {
    onClose();
    // Reset so re-opening starts from the confirmation step (fresh consent).
    setResult(null);
    run.reset();
  }

  return (
    <Sheet
      open={open}
      onClose={handleClose}
      title={t("negotiateTitle")}
      size="md"
      overlayBlur={false}
      closeLabel={t("close")}
    >
      <div className="space-y-4">
        <p className="text-xs leading-relaxed text-[var(--text-muted)]">
          {t("negotiateIntro")}
        </p>

        {result === null ? (
          // Confirmation step — energy cost shown BEFORE running.
          <div className="space-y-3">
            <AiEnergyHint />
            <div className="rounded-xl border border-[var(--border-default)] bg-[var(--surface-secondary)] px-3.5 py-3">
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {t("confirmTitle")}
              </p>
              <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">
                {t("confirmBody")}
              </p>
            </div>
            {run.isError && (
              <p role="alert" className="flex items-center gap-1.5 text-xs text-[var(--brand-red)]">
                <WarningCircle aria-hidden weight="duotone" className="size-4 shrink-0" />
                {t("errorBody")}
              </p>
            )}
            <div className="flex items-center gap-2.5">
              <Button variant="primary" loading={run.isPending} onClick={() => run.mutate()}>
                <Sparkle aria-hidden weight="fill" className="size-4" />
                {run.isPending ? t("running") : t("confirmRun")}
              </Button>
              <Button variant="ghost" onClick={handleClose} disabled={run.isPending}>
                {t("cancel")}
              </Button>
            </div>
          </div>
        ) : (
          <NegotiationResult result={result} t={t} />
        )}
      </div>
    </Sheet>
  );
}

function NegotiationResult({
  result,
  t,
}: {
  result: OfferNegotiationResult;
  t: ReturnType<typeof useTranslations<"applications.offerCompare">>;
}) {
  return (
    <div className="space-y-4">
      {result.ai_available && result.guidance ? (
        <section>
          <h3 className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-[var(--text-primary)]">
            <Sparkle aria-hidden weight="duotone" className="size-4 text-[var(--brand-primary)]" />
            {t("guidanceTitle")}
          </h3>
          <p className="whitespace-pre-line rounded-xl border border-[var(--border-default)] bg-[var(--surface-secondary)] px-3.5 py-3 text-xs leading-relaxed text-[var(--text-secondary)]">
            {result.guidance}
          </p>
        </section>
      ) : (
        <p className="flex items-start gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--surface-secondary)] px-3.5 py-2.5 text-xs leading-relaxed text-[var(--text-secondary)]">
          <WarningCircle aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0 text-[var(--text-muted)]" />
          {t("aiUnavailable")}
        </p>
      )}

      {result.tips.length > 0 && (
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("tipsTitle")}
          </h3>
          <ul className="space-y-1.5">
            {result.tips.map((tip, i) => (
              <li
                key={`tip-${i}`}
                className="flex items-start gap-2 rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-2 text-xs leading-relaxed text-[var(--text-secondary)]"
              >
                <Lightbulb aria-hidden weight="duotone" className="mt-0.5 size-3.5 shrink-0 text-[var(--amber-600)]" />
                {tip}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ALWAYS-ON disclaimer (server-localized) — never a guaranteed outcome. */}
      <p className="flex items-start gap-2 rounded-lg border border-[var(--amber-100)] bg-[var(--amber-50)]/60 px-3 py-2.5 text-[11px] leading-relaxed text-[var(--amber-700)]">
        <Handshake aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0" />
        {result.disclaimer}
      </p>
    </div>
  );
}
