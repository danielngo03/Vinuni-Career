"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { fitColor, fitTextColor } from "@/lib/cv/fit";
import {
  usePrefersReducedMotion,
  useMountAnimation,
} from "@/lib/hooks/use-mount-animation";
import { cn } from "@/lib/utils";

type RingSize = "sm" | "md";

/**
 * Per-card CV-fit score, drawn as a circular progress ring whose arc and centre
 * number are coloured by the deterministic 3-band product score (red/amber/green
 * from `fitColor`/`fitTextColor`). Never renders provider/model/confidence
 * internals — the score is a product fit signal only.
 *
 * On mount the arc sweeps 0 → score (~800ms ease-out) and the number counts up.
 * When the user prefers reduced motion it renders the final state instantly.
 */
export function FitScoreRing({
  score,
  size = "md",
  className,
}: {
  score: number;
  size?: RingSize;
  className?: string;
}) {
  const tf = useTranslations("cvFit");
  const reduced = usePrefersReducedMotion();
  const animated = useMountAnimation(reduced);

  // Geometry: viewBox 44×44, r=18 → circumference 2πr.
  const R = 18;
  const CIRC = 2 * Math.PI * R; // ≈ 113.097
  const target = Math.max(0, Math.min(100, Math.round(score)));
  const shownArc = animated ? target : 0;
  const dash = (shownArc / 100) * CIRC;
  const arcColor = fitColor(target);
  const textColor = fitTextColor(target);

  const strokeW = size === "sm" ? 4 : 4.5;
  const boxCls = size === "sm" ? "size-10" : "size-[3.25rem]";
  const numberCls =
    size === "sm"
      ? "text-[13px] font-extrabold leading-none tabular-nums"
      : "text-base font-extrabold leading-none tabular-nums";
  const unitCls =
    size === "sm"
      ? "text-[7px] font-semibold leading-none"
      : "text-[8px] font-semibold leading-none";

  // Count-up number mirrors the arc when motion is allowed.
  const [display, setDisplay] = useState(reduced ? target : 0);
  useEffect(() => {
    if (reduced) {
      setDisplay(target);
      return;
    }
    const durationMs = 800;
    const start = performance.now();
    let raf = 0;
    const step = (now: number) => {
      const p = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - p, 3); // ease-out cubic
      setDisplay(Math.round(eased * target));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, reduced]);

  return (
    <div
      className={cn("relative shrink-0", boxCls, className)}
      role="img"
      aria-label={tf("scoreAria", { score: target })}
    >
      <svg viewBox="0 0 44 44" className="size-full -rotate-90" aria-hidden>
        <circle
          cx="22"
          cy="22"
          r={R}
          fill="none"
          stroke="var(--bg-muted)"
          strokeWidth={strokeW}
        />
        <circle
          cx="22"
          cy="22"
          r={R}
          fill="none"
          stroke={arcColor}
          strokeWidth={strokeW}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${CIRC}`}
          style={{
            transition: reduced
              ? "none"
              : "stroke-dasharray 800ms cubic-bezier(0.22,1,0.36,1)",
          }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={numberCls} style={{ color: textColor }}>
          {display}
        </span>
        <span className={cn(unitCls, "text-[var(--text-muted)]")}>/100</span>
      </div>
    </div>
  );
}

/** Ring-shaped placeholder shown while the batch fit score is loading. */
export function FitScoreRingSkeleton({
  size = "md",
  className,
}: {
  size?: RingSize;
  className?: string;
}) {
  const boxCls = size === "sm" ? "size-10" : "size-[3.25rem]";
  return (
    <div
      aria-hidden
      className={cn(
        "shrink-0 animate-pulse rounded-full border-4 border-[var(--bg-muted)]",
        boxCls,
        className,
      )}
    />
  );
}
