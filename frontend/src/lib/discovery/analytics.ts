import { discoveryApi } from "@/lib/api";
import type {
  CoarseSignalTags,
  DiscoveryEventInput,
  DiscoverySourceSurface,
  RecoSource,
} from "@/lib/api";

/**
 * Client-side discovery analytics: privacy-safe, fire-and-forget. Never blocks
 * render, never sends PII (only the coded fields the backend allowlist accepts),
 * and de-dupes by idempotency key so an impression fires at most once per mount
 * even under React StrictMode double-invocation or repeated observer callbacks.
 */

// In-memory dedupe ledger for the current page session (cleared on full reload).
const sentKeys = new Set<string>();

/** Coarse device class for layout + allowed ad targeting (privacy-safe). */
export function deviceType(): "mobile" | "tablet" | "desktop" {
  if (typeof window === "undefined") return "desktop";
  const w = window.innerWidth;
  if (w < 640) return "mobile";
  if (w < 1024) return "tablet";
  return "desktop";
}

/** The active locale, read from the document lang (set by next-intl). */
function currentLocale(): string | undefined {
  if (typeof document === "undefined") return undefined;
  return document.documentElement.lang || undefined;
}

/**
 * Record a discovery event. Fire-and-forget: returns immediately, swallows all
 * errors, and de-dupes by `idempotency_key`. On transport failure the key is
 * released so a later interaction can retry.
 */
export function recordDiscoveryEvent(input: DiscoveryEventInput): void {
  if (typeof window === "undefined") return;
  if (sentKeys.has(input.idempotency_key)) return;
  sentKeys.add(input.idempotency_key);

  const payload: DiscoveryEventInput = {
    ...input,
    locale: input.locale ?? currentLocale(),
    signal_tags: enrichSignals(input.signal_tags),
  };

  void discoveryApi.recordEvent(payload).then((ok) => {
    if (!ok) sentKeys.delete(input.idempotency_key);
  });
}

/** Always attach the coarse device class; keep everything else as supplied. */
function enrichSignals(tags?: CoarseSignalTags): CoarseSignalTags | undefined {
  const base: CoarseSignalTags = { ...(tags ?? {}), device_type: deviceType() };
  return base;
}

/* ---------------------------- Surface resolution -------------------------- */

/**
 * Map a rail base + ranking source to the inventory-classed analytics surface.
 * Sponsored items override to the sponsored surface (and carry `placement_id`);
 * organic/recommended map to their own surfaces so the four inventory classes
 * stay separately tracked.
 */
export function railSurface(
  base: "homepage" | "search",
  source: RecoSource,
): DiscoverySourceSurface {
  if (source === "sponsored") {
    return base === "homepage" ? "homepage_sponsored" : "search_sponsored";
  }
  if (source === "recommended") {
    return base === "homepage" ? "homepage_recommended" : "search_recommended";
  }
  if (source === "popular" && base === "homepage") return "homepage_popular";
  // recent / popular(search) fallbacks -> organic surface for that base.
  return base === "homepage" ? "homepage_recent" : "search";
}
