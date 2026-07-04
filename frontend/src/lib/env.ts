/**
 * Public runtime config. Only NEXT_PUBLIC_* values are allowed on the client
 * (docs/ENVIRONMENT.md §9). Values are read from frontend/.env.
 */
export const env = {
  appUrl: process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000",
  apiBaseUrl:
    process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1",
  defaultLocale: process.env.NEXT_PUBLIC_DEFAULT_LOCALE ?? "vi",
  supportedLocales: (process.env.NEXT_PUBLIC_SUPPORTED_LOCALES ?? "vi,en")
    .split(",")
    .map((l) => l.trim())
    .filter(Boolean),
  browserLocaleDetection:
    (process.env.NEXT_PUBLIC_BROWSER_LOCALE_DETECTION ?? "true") === "true",
} as const;
