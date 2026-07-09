import { env } from "@/lib/env";

/**
 * Resolve the API base to an absolute origin. `env.apiBaseUrl` may be absolute
 * (`http://host/api/v1`) or a same-origin proxy path (`/api/v1`); the latter is
 * resolved against the browser origin.
 */
function absoluteApiBase(): string {
  const base = env.apiBaseUrl.replace(/\/$/, "");
  if (/^https?:\/\//.test(base)) return base;
  const origin =
    typeof window !== "undefined" ? window.location.origin : "http://localhost:3000";
  return `${origin}${base.startsWith("/") ? base : `/${base}`}`;
}

/** Absolute HTTP(S) URL for an API path (used by the XHR attachment upload). */
export function apiHttpUrl(path: string): string {
  const base = absoluteApiBase();
  return `${base}${path.startsWith("/") ? path : `/${path}`}`;
}

/**
 * Absolute WS(S) URL for an API path. `http`→`ws` / `https`→`wss`, keeping the
 * same-origin proxy prefix so the messaging socket rides the existing route.
 */
export function apiWsUrl(path: string): string {
  return apiHttpUrl(path).replace(/^http/, "ws");
}
