import { NextResponse } from "next/server";
import type { TokenResponse } from "@/lib/api/types";
import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  sessionCookieOptions,
} from "@/lib/auth/cookies";

const API_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000/api/v1";

export async function POST(request: Request) {
  const refresh = request.headers
    .get("cookie")
    ?.match(new RegExp(`${REFRESH_COOKIE}=([^;]+)`))?.[1];
  if (!refresh) {
    return NextResponse.json({ detail: "Missing refresh session" }, { status: 401 });
  }
  const response = await fetch(`${API_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: decodeURIComponent(refresh) }),
    cache: "no-store",
  });
  const body = await response.json();
  if (!response.ok) return NextResponse.json(body, { status: response.status });

  const token = body as TokenResponse;
  const result = NextResponse.json({ refreshed: true });
  result.cookies.set(
    ACCESS_COOKIE,
    token.access_token,
    sessionCookieOptions(60 * 60),
  );
  if (token.refresh_token) {
    result.cookies.set(
      REFRESH_COOKIE,
      token.refresh_token,
      sessionCookieOptions(60 * 60 * 24 * 14),
    );
  }
  return result;
}
