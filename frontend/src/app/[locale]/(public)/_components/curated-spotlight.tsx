"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import { useTranslations } from "next-intl";
import { ArrowRight, SealCheck } from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { cn } from "@/lib/utils";

/**
 * The VinUni Curated Spotlight — the marketplace's editorial masthead and the
 * page's signature element. University-CURATED slides (not paid) carry a navy
 * "VinUni tuyển chọn" ribbon over real campus / career-day imagery from
 * `public/images`. Slides cross-fade on a 6s timer (paused on hover/focus and
 * frozen entirely under prefers-reduced-motion), with manual dots. Every slide
 * links to a real route — no fabricated data claims.
 */
interface Slide {
  key: string;
  image: string;
  href: string;
}

const SLIDES: Slide[] = [
  { key: "careerDay", image: "/images/career-day-2026.jpg", href: "/events" },
  { key: "employers", image: "/images/vinuni-campus.png", href: "/companies" },
];

const INTERVAL = 6000;

export function CuratedSpotlight() {
  const t = useTranslations("marketplace.spotlight");
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const reduced = useRef(false);

  useEffect(() => {
    reduced.current =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }, []);

  useEffect(() => {
    if (paused || reduced.current || SLIDES.length < 2) return;
    const id = window.setInterval(
      () => setIndex((i) => (i + 1) % SLIDES.length),
      INTERVAL,
    );
    return () => window.clearInterval(id);
  }, [paused]);

  return (
    <section
      aria-label={t("regionLabel")}
      aria-roledescription="carousel"
      className="career-container pt-6"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
    >
      <div className="relative overflow-hidden rounded-2xl bg-[var(--brand-navy)] shadow-[var(--shadow-lg)]">
        <div className="relative aspect-[16/7] w-full sm:aspect-[21/7]">
          {SLIDES.map((slide, i) => (
            <div
              key={slide.key}
              aria-hidden={i !== index}
              className={cn(
                "absolute inset-0 transition-opacity duration-700",
                i === index ? "opacity-100" : "pointer-events-none opacity-0",
              )}
            >
              <Image
                src={slide.image}
                alt=""
                fill
                priority={i === 0}
                sizes="(min-width: 1280px) 1232px, 100vw"
                className="object-cover"
              />
              {/* Navy editorial scrim — keeps copy legible, ties to the brand. */}
              <div
                aria-hidden
                className="absolute inset-0 bg-gradient-to-r from-[var(--brand-navy)] via-[var(--brand-navy)]/80 to-transparent"
              />
              <div className="absolute inset-0 flex items-center">
                <div className="max-w-xl px-5 py-6 sm:px-10">
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-[0.6875rem] font-semibold uppercase tracking-[0.12em] text-[var(--blue-100)] ring-1 ring-inset ring-white/20 backdrop-blur">
                    <SealCheck aria-hidden weight="fill" className="size-3.5" />
                    {t("ribbon")}
                  </span>
                  <h2 className="mt-3 text-2xl font-black leading-tight tracking-tight text-white sm:text-3xl">
                    {t(`${slide.key}.title`)}
                  </h2>
                  <p className="mt-2 max-w-md text-sm font-medium text-[var(--blue-100)] sm:text-base">
                    {t(`${slide.key}.subtitle`)}
                  </p>
                  <Link
                    href={slide.href}
                    className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-white px-4 py-2 text-sm font-semibold text-[var(--brand-navy)] outline-none transition-colors hover:bg-[var(--blue-50)] focus-visible:ring-2 focus-visible:ring-white/70"
                  >
                    {t(`${slide.key}.cta`)}
                    <ArrowRight aria-hidden weight="bold" className="size-4" />
                  </Link>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Dots */}
        {SLIDES.length > 1 && (
          <div className="absolute bottom-3 right-4 flex items-center gap-1.5">
            {SLIDES.map((slide, i) => (
              <button
                key={slide.key}
                type="button"
                aria-label={t("goTo", { n: i + 1 })}
                aria-current={i === index}
                onClick={() => setIndex(i)}
                className={cn(
                  "h-1.5 rounded-full outline-none transition-all focus-visible:ring-2 focus-visible:ring-white/70",
                  i === index
                    ? "w-6 bg-white"
                    : "w-1.5 bg-white/40 hover:bg-white/70",
                )}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
