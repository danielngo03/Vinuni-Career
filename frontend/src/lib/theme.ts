"use client";

import { useCallback, useEffect, useState } from "react";

export type ThemePref = "light" | "dark" | "system";
const STORAGE_KEY = "vinuni-theme";

function resolve(pref: ThemePref): "light" | "dark" {
  if (pref === "system") {
    return typeof window !== "undefined" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }
  return pref;
}

function apply(pref: ThemePref) {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.theme = resolve(pref);
}

/**
 * Light/dark/system theme with localStorage persistence (DESIGN.md §8).
 * Light is the default; tokens swap via [data-theme]. Reduced motion honored
 * globally in CSS.
 */
export function useTheme() {
  const [pref, setPref] = useState<ThemePref>("light");

  useEffect(() => {
    const stored = (localStorage.getItem(STORAGE_KEY) as ThemePref) ?? "light";
    setPref(stored);
    apply(stored);
  }, []);

  // In "system" mode, follow live OS theme changes (not just at load).
  useEffect(() => {
    if (pref !== "system" || typeof window === "undefined") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => apply("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [pref]);

  const setTheme = useCallback((next: ThemePref) => {
    setPref(next);
    localStorage.setItem(STORAGE_KEY, next);
    apply(next);
  }, []);

  return { theme: pref, setTheme };
}
