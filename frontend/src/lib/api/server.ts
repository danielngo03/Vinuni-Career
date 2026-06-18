import { cookies } from "next/headers";
import { ACCESS_COOKIE, IDENTITY_COOKIE } from "@/lib/auth/cookies";

const API_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000/api/v1";

export class BackendError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function backendFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const cookieStore = await cookies();
  const token = cookieStore.get(ACCESS_COOKIE)?.value;
  const identity = cookieStore.get(IDENTITY_COOKIE)?.value;
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (identity) headers.set("X-Identity-Id", identity);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });

  if (!response.ok) {
    let message = `Backend request failed (${response.status})`;
    try {
      const body = (await response.json()) as {
        detail?: string;
        error?: { message?: string };
      };
      message = body.detail || body.error?.message || message;
    } catch {
      // Keep the stable fallback message.
    }
    throw new BackendError(message, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
