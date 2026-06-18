"use client";

export class ApiClientError extends Error {
  constructor(
    message: string,
    public status: number,
    public details?: unknown,
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`/api/backend${path}`, {
    ...init,
    headers,
    credentials: "same-origin",
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    let details: unknown;
    try {
      const body = (await response.json()) as {
        detail?: string;
        error?: { message?: string; details?: unknown };
      };
      message = body.error?.message || body.detail || message;
      details = body.error?.details;
    } catch {
      // Preserve the stable fallback for non-JSON upstream errors.
    }
    throw new ApiClientError(message, response.status, details);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function apiMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}
