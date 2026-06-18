import { NextResponse } from "next/server";
import type { TokenResponse } from "@/lib/api/types";
import {
  ACCESS_COOKIE,
  IDENTITY_COOKIE,
  PORTAL_COOKIE,
  REFRESH_COOKIE,
  sessionCookieOptions,
} from "@/lib/auth/cookies";

const API_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000/api/v1";

export async function POST(request: Request) {
  const payload = await request.json();
  const response = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  const body = await response.json();
  if (!response.ok) {
    return NextResponse.json(body, { status: response.status });
  }

  const token = body as TokenResponse;
  const result = NextResponse.json({
    user: token.user,
    identities: token.identities,
    access_scope: token.access_scope,
    pending_registration_id: token.pending_registration_id,
  });
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
  if (token.identities.length === 1) {
    const identity = token.identities[0];
    result.cookies.set(
      IDENTITY_COOKIE,
      identity.id,
      sessionCookieOptions(60 * 60 * 24 * 14),
    );
    result.cookies.set(
      PORTAL_COOKIE,
      identity.portal,
      sessionCookieOptions(60 * 60 * 24 * 14),
    );
  }
  return result;
}
