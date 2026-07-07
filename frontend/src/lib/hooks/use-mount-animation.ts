"use client";

import { useEffect, useState } from "react";

/** Detect the reduced-motion preference once on mount (SSR-safe). */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener?.("change", onChange);
    return () => mq.removeEventListener?.("change", onChange);
  }, []);
  return reduced;
}

/**
 * Toggles from `false` to `true` on the first paint after mount so CSS
 * transitions animate from a 0 baseline up to the real value. When motion is
 * reduced it returns `true` immediately (final state, no animation).
 */
export function useMountAnimation(reduced: boolean): boolean {
  const [animated, setAnimated] = useState(false);
  useEffect(() => {
    if (reduced) {
      setAnimated(true);
      return;
    }
    const id = requestAnimationFrame(() =>
      requestAnimationFrame(() => setAnimated(true)),
    );
    return () => cancelAnimationFrame(id);
  }, [reduced]);
  return reduced ? true : animated;
}
