"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, ArrowLeft, SealCheck } from "@phosphor-icons/react";
import Image from "next/image";
import { Link } from "@/i18n/navigation";
import { marketplaceApi } from "@/lib/api";
import { Skeleton } from "@/components/ui";

const AUTO_INTERVAL = 5500;
const SWIPE_THRESHOLD = 50;

// Neutral ink base for the editorial employer spotlight. Monochrome by design —
// the campus photo and company logo carry the visual interest, not color.
const BASE = "from-[var(--gray-900)] to-[var(--gray-950)]";

export function PartnerBannerSlider() {
  const t = useTranslations("marketplace.partnerBanner");
  const { data, isPending } = useQuery({
    queryKey: ["marketplace", "overview"],
    queryFn: () => marketplaceApi.overview(),
    retry: false,
    staleTime: 60_000,
  });

  const companies = data?.employer_spotlight ?? [];
  const n = companies.length;

  const [idx, setIdx] = useState(0);
  const [paused, setPaused] = useState(false);
  const [animKey, setAnimKey] = useState(0);

  const pointerStartX = useRef(0);

  const go = useCallback((to: number) => {
    setIdx(((to % n) + n) % n);
    setAnimKey((k) => k + 1);
  }, [n]);

  useEffect(() => {
    if (paused || n < 2) return;
    const id = setInterval(() => go(idx + 1), AUTO_INTERVAL);
    return () => clearInterval(id);
  }, [paused, n, idx, go]);

  const onPointerDown = (e: React.PointerEvent) => {
    pointerStartX.current = e.clientX;
  };
  const onPointerUp = (e: React.PointerEvent) => {
    const dx = e.clientX - pointerStartX.current;
    if (dx < -SWIPE_THRESHOLD) go(idx + 1);
    else if (dx > SWIPE_THRESHOLD) go(idx - 1);
  };

  /* ── Loading ── */
  if (isPending) {
    return (
      <div className={`relative h-[420px] overflow-hidden rounded-[24px] bg-gradient-to-b ${BASE}`}>
        <Image
          src="/images/vinuni-campus.png"
          alt=""
          fill
          sizes="(max-width: 1024px) 100vw, 65vw"
          className="pointer-events-none object-cover opacity-20"
          priority
        />
        <div className="relative flex h-full flex-col justify-center px-10">
          <Skeleton className="mb-3 h-4 w-24 bg-white/10" />
          <Skeleton className="mb-3 h-9 w-3/4 bg-white/10" />
          <Skeleton className="mb-1 h-4 w-1/2 bg-white/10" />
          <Skeleton className="mt-5 h-9 w-40 bg-white/10" />
        </div>
      </div>
    );
  }

  /* ── Empty ── */
  if (n === 0) {
    return (
      <div className={`relative h-[420px] overflow-hidden rounded-[24px] bg-gradient-to-b ${BASE}`}>
        <Image
          src="/images/vinuni-campus.png"
          alt=""
          fill
          sizes="(max-width: 1024px) 100vw, 65vw"
          className="pointer-events-none object-cover opacity-25"
          priority
        />
        <div className="relative flex h-full flex-col justify-center px-8 lg:px-10">
          <span className="mb-3 text-[0.65rem] font-bold uppercase tracking-widest text-white/60">
            {t("centerLabel")}
          </span>
          <h2 className="text-[2.2rem] font-black leading-tight text-white">
            {t("emptyHeadline")}
          </h2>
          <p className="mt-2 text-sm text-white/55">
            {t("emptySubtitle")}
          </p>
          <Link
            href="/companies"
            className="mt-6 inline-flex w-fit items-center gap-2 rounded-xl bg-white/10 px-5 py-2.5 text-sm font-semibold text-white ring-1 ring-white/20 backdrop-blur-sm transition-all hover:bg-white/18"
          >
            {t("emptyViewPartners")} <ArrowRight aria-hidden weight="bold" className="size-4" />
          </Link>
        </div>
      </div>
    );
  }

  const company = companies[idx]!;

  return (
    <div
      className="group relative h-[420px] select-none overflow-hidden rounded-[24px]"
      style={{ boxShadow: "0 16px 56px -4px rgba(0,0,0,0.45), 0 0 0 1px rgba(255,255,255,0.10)" }}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onPointerDown={onPointerDown}
      onPointerUp={onPointerUp}
      aria-roledescription="carousel"
      aria-label={t("ariaLabel")}
    >
      {/* ── Backgrounds ── */}
      <div className={`absolute inset-0 bg-gradient-to-b ${BASE}`} />
      <Image
        src="/images/vinuni-campus.png"
        alt=""
        fill
        sizes="(max-width: 1024px) 100vw, 65vw"
        className="pointer-events-none object-cover opacity-[0.12]"
        priority
      />

      {/* Logo watermarks — crossfade between companies */}
      {companies.map((c, i) =>
        c.logo_url ? (
          <div
            key={c.id}
            className="pointer-events-none absolute right-0 bottom-0 top-0 w-2/5 overflow-hidden transition-opacity duration-700"
            style={{ opacity: i === idx ? 0.07 : 0 }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={c.logo_url}
              alt=""
              className="h-full w-full object-contain object-right"
            />
          </div>
        ) : null
      )}

      {/* ── Content — key change resets stagger animation ── */}
      <div
        key={animKey}
        className="relative z-10 flex h-full flex-col justify-center px-8 lg:px-10"
      >
        <div className="flex max-w-[520px] flex-col">
          <span
            className="inline-flex w-fit items-center gap-1.5 rounded-full border border-white/12 bg-white/8 px-3 py-1 text-[0.65rem] font-semibold uppercase tracking-[0.14em] text-white/65 backdrop-blur-sm"
            style={{ animation: "pSlideUp 0.55s cubic-bezier(0.16,1,0.3,1) 0ms both" }}
          >
            {company.is_verified && (
              <SealCheck aria-hidden weight="fill" className="size-3 text-[var(--teal-500)]" />
            )}
            {t("verifiedBadge")}
          </span>

          <h2
            className="mt-5 text-[2.1rem] font-black leading-[1.1] tracking-tight text-white lg:text-[2.55rem]"
            style={{ animation: "pSlideUp 0.55s cubic-bezier(0.16,1,0.3,1) 75ms both" }}
          >
            {company.display_name}
          </h2>

          {company.industry && (
            <p
              className="mt-2 text-sm font-medium text-white/50"
              style={{ animation: "pSlideUp 0.55s cubic-bezier(0.16,1,0.3,1) 145ms both" }}
            >
              {company.industry}
            </p>
          )}

          <div
            style={{ animation: "pSlideUp 0.55s cubic-bezier(0.16,1,0.3,1) 210ms both" }}
          >
            <Link
              href={`/companies/${company.slug}`}
              className="mt-7 inline-flex items-center gap-2.5 rounded-xl bg-white/10 px-5 py-2.5 text-sm font-semibold text-white ring-1 ring-inset ring-white/18 outline-none backdrop-blur-sm transition-all hover:bg-white/18 hover:ring-white/32 focus-visible:ring-2 focus-visible:ring-white/60"
            >
              {t("viewOpportunities")}
              <ArrowRight aria-hidden weight="bold" className="size-4" />
            </Link>
          </div>
        </div>
      </div>

      {/* ── Slide counter ── */}
      {n > 1 && (
        <div className="absolute right-6 top-5 z-10 flex items-baseline gap-1 text-white/40">
          <span className="text-[0.85rem] font-bold tabular-nums text-white/80">
            {String(idx + 1).padStart(2, "0")}
          </span>
          <span className="text-[0.7rem]">—</span>
          <span className="text-[0.75rem] tabular-nums">
            {String(n).padStart(2, "0")}
          </span>
        </div>
      )}

      {/* ── Arrow navigation (fade in on hover) ── */}
      {n > 1 && (
        <>
          <button
            type="button"
            aria-label={t("prevSlide")}
            onClick={(e) => { e.stopPropagation(); go(idx - 1); }}
            className="absolute left-4 top-1/2 z-10 -translate-y-1/2 flex size-9 items-center justify-center rounded-full bg-white/10 text-white ring-1 ring-white/15 backdrop-blur-sm outline-none transition-all hover:bg-white/22 focus-visible:ring-2 focus-visible:ring-white/60 opacity-0 group-hover:opacity-100"
            style={{ transition: "opacity 0.2s ease, background-color 0.15s ease" }}
          >
            <ArrowLeft aria-hidden weight="bold" className="size-4" />
          </button>
          <button
            type="button"
            aria-label={t("nextSlide")}
            onClick={(e) => { e.stopPropagation(); go(idx + 1); }}
            className="absolute right-4 top-1/2 z-10 -translate-y-1/2 flex size-9 items-center justify-center rounded-full bg-white/10 text-white ring-1 ring-white/15 backdrop-blur-sm outline-none transition-all hover:bg-white/22 focus-visible:ring-2 focus-visible:ring-white/60 opacity-0 group-hover:opacity-100"
            style={{ transition: "opacity 0.2s ease, background-color 0.15s ease" }}
          >
            <ArrowRight aria-hidden weight="bold" className="size-4" />
          </button>
        </>
      )}

      {/* ── Auto-progress bar ── */}
      {n > 1 && !paused && (
        <div
          key={`pb-${animKey}`}
          aria-hidden
          className="absolute bottom-0 left-0 h-[2px] rounded-r-full bg-white/35"
          style={{ animation: `pProgress ${AUTO_INTERVAL}ms linear forwards` }}
        />
      )}

      <style>{`
        @keyframes pSlideUp {
          from { opacity: 0; transform: translateY(12px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes pProgress {
          from { width: 0%; }
          to   { width: 100%; }
        }
      `}</style>
    </div>
  );
}
