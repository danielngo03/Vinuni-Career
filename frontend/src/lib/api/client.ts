import { env } from "@/lib/env";
import { ApiError, normalizeCode } from "./errors";
import type {
  ApiEnvelope,
  ApiErrorBody,
  ApiListEnvelope,
} from "./types";

/**
 * Pluggable access-token source, registered by the session layer at app start.
 * Returns the in-memory access token (never read from storage). Every request
 * also sends `credentials: "include"` (see {@link apiFetch}/{@link apiUpload}),
 * so the httpOnly refresh cookie (`vinuni_refresh`) travels automatically with
 * refresh/logout/identity calls without any token handling in JS.
 */
let tokenSource: () => string | null | Promise<string | null> = () => null;

export function setTokenSource(
  source: () => string | null | Promise<string | null>,
): void {
  tokenSource = source;
}

/**
 * Refresh handler invoked once on a 401 before retrying the request. Registered
 * by the session layer to avoid a circular import. Returns true if a new access
 * token was obtained.
 */
let refreshHandler: (() => Promise<boolean>) | null = null;

export function setRefreshHandler(handler: () => Promise<boolean>): void {
  refreshHandler = handler;
}

export interface RequestOptions extends Omit<RequestInit, "body"> {
  /** JSON body — serialized automatically. */
  json?: unknown;
  /** Query params appended to the URL. */
  query?: Record<string, string | number | boolean | undefined | null>;
  /** Skip auth header injection (public endpoints). */
  skipAuth?: boolean;
  /** Skip the one-shot refresh-and-retry on 401 (used by the refresh call itself). */
  skipRefresh?: boolean;
}

function buildUrl(
  path: string,
  query?: RequestOptions["query"],
): string {
  const base = env.apiBaseUrl.replace(/\/$/, "");
  // Resolve relative base URLs (e.g. "/api/v1" for the same-origin proxy) using
  // the browser's own origin so new URL() doesn't throw on a bare path.
  const origin =
    typeof window !== "undefined" ? window.location.origin : "http://localhost:3000";
  const absolute = path.startsWith("http")
    ? path
    : `${base}${path.startsWith("/") ? "" : "/"}${path}`;
  const url = new URL(absolute.startsWith("/") ? `${origin}${absolute}` : absolute);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null) {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

async function parseError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody | undefined;
  try {
    body = (await response.json()) as ApiErrorBody;
  } catch {
    body = undefined;
  }

  const code = normalizeCode(body?.error?.code);
  // User-safe message only. If the server did not provide one, use a generic
  // string; the UI layer maps codes to localized copy.
  const message =
    body?.error?.message ?? "Đã xảy ra lỗi. Vui lòng thử lại.";

  return new ApiError({
    code,
    message,
    status: response.status,
    requestId: body?.error?.request_id,
    details: body?.error?.details,
  });
}

/**
 * Core typed fetch wrapper. Returns parsed JSON; throws ApiError on non-2xx
 * or network failure. Never leaks raw upstream/provider internals to callers.
 */
export async function apiFetch<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { json, query, skipAuth, skipRefresh, headers, ...rest } = options;
  const url = buildUrl(path, query);

  const send = async (): Promise<Response> => {
    const finalHeaders = new Headers(headers);
    finalHeaders.set("Accept", "application/json");
    if (json !== undefined) {
      finalHeaders.set("Content-Type", "application/json");
    }
    if (!skipAuth) {
      const token = await tokenSource();
      if (token) finalHeaders.set("Authorization", `Bearer ${token}`);
    }
    return fetch(url, {
      ...rest,
      headers: finalHeaders,
      credentials: "include",
      body: json !== undefined ? JSON.stringify(json) : undefined,
    });
  };

  const networkError = () =>
    new ApiError({
      code: "NETWORK_ERROR",
      message: "Unable to connect to the server. Please check your network connection.",
      status: 0,
    });

  let response: Response;
  try {
    response = await send();
  } catch {
    // Connection refused / DNS / offline — generic, user-safe.
    throw networkError();
  }

  // One-shot auto-refresh: on a 401, try to mint a fresh access token and retry
  // the original request exactly once before surfacing an auth error.
  if (
    response.status === 401 &&
    !skipAuth &&
    !skipRefresh &&
    refreshHandler
  ) {
    const refreshed = await refreshHandler();
    if (refreshed) {
      try {
        response = await send();
      } catch {
        throw networkError();
      }
    }
  }

  if (response.status === 204) {
    return undefined as T;
  }

  if (!response.ok) {
    throw await parseError(response);
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError({
      code: "UNKNOWN_ERROR",
      message: "Invalid response from server.",
      status: response.status,
    });
  }
}

/**
 * Multipart/form-data upload with the same auth, one-shot 401 refresh-retry,
 * and leak-safe error mapping as {@link apiFetch}. The browser sets the
 * multipart boundary, so we never set Content-Type here.
 */
export async function apiUpload<T>(
  path: string,
  form: FormData,
  options: { skipRefresh?: boolean; method?: "POST" | "PATCH" | "PUT" } = {},
): Promise<T> {
  const url = buildUrl(path);

  const send = async (): Promise<Response> => {
    const finalHeaders = new Headers();
    finalHeaders.set("Accept", "application/json");
    const token = await tokenSource();
    if (token) finalHeaders.set("Authorization", `Bearer ${token}`);
    return fetch(url, {
      method: options.method ?? "POST",
      headers: finalHeaders,
      credentials: "include",
      body: form,
    });
  };

  const networkError = () =>
    new ApiError({
      code: "NETWORK_ERROR",
      message: "Unable to connect to the server. Please check your network connection.",
      status: 0,
    });

  let response: Response;
  try {
    response = await send();
  } catch {
    throw networkError();
  }

  if (response.status === 401 && !options.skipRefresh && refreshHandler) {
    const refreshed = await refreshHandler();
    if (refreshed) {
      try {
        response = await send();
      } catch {
        throw networkError();
      }
    }
  }

  if (!response.ok) {
    throw await parseError(response);
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError({
      code: "UNKNOWN_ERROR",
      message: "Invalid response from server.",
      status: response.status,
    });
  }
}

/**
 * Download a file (CSV, PDF, etc.) from an authenticated endpoint.
 * Same auth + one-shot refresh logic as {@link apiUpload}; returns a Blob
 * instead of parsing JSON. Throws {@link ApiError} on non-2xx or network fail.
 */
export async function apiDownload(
  path: string,
  options: Pick<RequestOptions, "query" | "skipRefresh"> = {},
): Promise<Blob> {
  const url = buildUrl(path, options.query);

  const send = async (): Promise<Response> => {
    const finalHeaders = new Headers();
    const token = await tokenSource();
    if (token) finalHeaders.set("Authorization", `Bearer ${token}`);
    return fetch(url, {
      method: "GET",
      headers: finalHeaders,
      credentials: "include",
    });
  };

  const networkError = () =>
    new ApiError({
      code: "NETWORK_ERROR",
      message: "Unable to connect to the server. Please check your network connection.",
      status: 0,
    });

  let response: Response;
  try {
    response = await send();
  } catch {
    throw networkError();
  }

  if (response.status === 401 && !options.skipRefresh && refreshHandler) {
    const refreshed = await refreshHandler();
    if (refreshed) {
      try {
        response = await send();
      } catch {
        throw networkError();
      }
    }
  }

  if (!response.ok) {
    throw await parseError(response);
  }

  return response.blob();
}

/** Convenience helpers for the standard envelopes in API_CONTRACTS.md. */
export const api = {
  async get<T>(path: string, options?: RequestOptions): Promise<T> {
    const res = await apiFetch<ApiEnvelope<T>>(path, {
      ...options,
      method: "GET",
    });
    return res.data;
  },
  async list<T>(
    path: string,
    options?: RequestOptions,
  ): Promise<ApiListEnvelope<T>> {
    return apiFetch<ApiListEnvelope<T>>(path, { ...options, method: "GET" });
  },
  async post<T>(path: string, json?: unknown, options?: RequestOptions): Promise<T> {
    const res = await apiFetch<ApiEnvelope<T>>(path, {
      ...options,
      method: "POST",
      json,
    });
    return res.data;
  },
  async patch<T>(path: string, json?: unknown, options?: RequestOptions): Promise<T> {
    const res = await apiFetch<ApiEnvelope<T>>(path, {
      ...options,
      method: "PATCH",
      json,
    });
    return res.data;
  },
  async put<T>(path: string, json?: unknown, options?: RequestOptions): Promise<T> {
    const res = await apiFetch<ApiEnvelope<T>>(path, {
      ...options,
      method: "PUT",
      json,
    });
    return res.data;
  },
  async delete<T>(path: string, options?: RequestOptions): Promise<T> {
    const res = await apiFetch<ApiEnvelope<T>>(path, {
      ...options,
      method: "DELETE",
    });
    return res.data;
  },
  /** Raw health probe (not enveloped). */
  async health(): Promise<{ status: string }> {
    return apiFetch<{ status: string }>("/health", { skipAuth: true });
  },
  /**
   * Raw authenticated file download (non-JSON responses, e.g. CSV export).
   * Returns the response Blob plus the server-suggested filename from
   * `Content-Disposition`. Throws {@link ApiError} on non-2xx.
   */
  async download(
    path: string,
    options?: RequestOptions,
  ): Promise<{ blob: Blob; filename: string | null }> {
    const url = buildUrl(path, options?.query);
    const headers = new Headers(options?.headers);
    if (!options?.skipAuth) {
      const token = await tokenSource();
      if (token) headers.set("Authorization", `Bearer ${token}`);
    }
    const res = await fetch(url, {
      ...options,
      method: "GET",
      headers,
      credentials: "include",
    });
    if (!res.ok) throw await parseError(res);
    const blob = await res.blob();
    const disposition = res.headers.get("Content-Disposition");
    const match = disposition?.match(/filename="?([^"]+)"?/);
    return { blob, filename: match?.[1] ?? null };
  },
};
