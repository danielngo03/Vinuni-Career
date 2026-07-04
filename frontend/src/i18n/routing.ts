import { defineRouting } from "next-intl/routing";

/**
 * Locale routing config.
 * Defaults mirror frontend/.env (NEXT_PUBLIC_DEFAULT_LOCALE=vi,
 * NEXT_PUBLIC_SUPPORTED_LOCALES=vi,en, NEXT_PUBLIC_BROWSER_LOCALE_DETECTION=true).
 * Kept static here because middleware/runtime config must be statically analyzable.
 */
export const routing = defineRouting({
  locales: ["vi", "en"],
  defaultLocale: "vi",
  // Detect Vietnamese browser preference, otherwise fall back to default.
  // Explicit user choice (locale prefix in URL / cookie) always overrides detection.
  localeDetection: true,
  localePrefix: "always",
});

export type AppLocale = (typeof routing.locales)[number];
