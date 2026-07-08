"use client";

import { apiFetch, setRefreshHandler, setTokenSource } from "./client";
import type { ApiEnvelope } from "./types";

/**
 * Session token handling.
 *
 * Strategy (documented in handoff):
 * - The short-lived ACCESS token is held in memory only. It is never written to
 *   localStorage/sessionStorage, so it is not readable by injected scripts and
 *   disappears on tab close.
 * - The REFRESH token is cookie-only. The backend sets an httpOnly cookie
 *   (`vinuni_refresh`, path `/api/v1/auth`) that JS can never read or write. The
 *   API client always sends `credentials: "include"`, so the cookie travels with
 *   refresh/logout/identity calls automatically. We never touch refresh-token
 *   material in JS, and never persist it anywhere on the client.
 * - A non-sensitive "session hint" flag (no token material) lets us decide
 *   whether to attempt a silent cookie refresh on load without a guaranteed-401
 *   round-trip for fresh guests.
 */

const HINT_KEY = "vinuni.session";

let accessToken: string | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

/** Access-token-only payload. The refresh token never reaches JS (cookie-only). */
export interface TokenPair {
  access_token: string;
}

export function setSession(tokens: TokenPair): void {
  accessToken = tokens.access_token;
  if (typeof window === "undefined") return;
  // Non-sensitive hint only — never any token material.
  localStorage.setItem(HINT_KEY, "1");
}

export function clearSession(): void {
  accessToken = null;
  if (typeof window === "undefined") return;
  localStorage.removeItem(HINT_KEY);
}

/** True when a previous session likely exists and silent refresh is worth trying. */
export function hasSessionHint(): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem(HINT_KEY) === "1";
}

let refreshing: Promise<boolean> | null = null;

/**
 * Exchange the httpOnly refresh cookie for a fresh access token. The cookie is
 * sent automatically via `credentials: "include"`; we send NO body. The backend
 * rotates the cookie on success. De-duplicated so concurrent 401s only trigger
 * one refresh round-trip.
 */
export async function refreshSession(): Promise<boolean> {
  if (refreshing) return refreshing;
  refreshing = (async () => {
    try {
      const res = await apiFetch<ApiEnvelope<TokenPair>>("/auth/refresh", {
        method: "POST",
        skipAuth: true,
        skipRefresh: true,
      });
      if (res?.data?.access_token) {
        setSession({ access_token: res.data.access_token });
        return true;
      }
      clearSession();
      return false;
    } catch {
      clearSession();
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

// Register the access-token accessor and the 401 refresh handler with the
// low-level client. Imported once (via providers) at app start.
setTokenSource(getAccessToken);
setRefreshHandler(refreshSession);
