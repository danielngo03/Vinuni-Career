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

export async function GET(request: Request) {
  const url = new URL(request.url);
  const ticket = url.searchParams.get("ticket");
  const locale =
    request.headers
      .get("cookie")
      ?.match(/vinuni_oidc_locale=([^;]+)/)?.[1] || "vi";
  if (!ticket) {
    return NextResponse.redirect(new URL(`/${locale}/login?error=oidc`, request.url));
  }
  const response = await fetch(`${API_URL}/auth/oidc/exchange`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ticket,
      device_info: request.headers.get("user-agent")?.slice(0, 200),
    }),
    cache: "no-store",
  });
  if (!response.ok) {
    return NextResponse.redirect(new URL(`/${locale}/login?error=oidc`, request.url));
  }
  const token = (await response.json()) as TokenResponse;
  const target =
    token.identities.length === 1
      ? `/${locale}/${token.identities[0].portal}`
      : `/${locale}/select-identity`;
  const result = NextResponse.redirect(new URL(target, request.url));
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
  result.cookies.set("vinuni_oidc_locale", "", {
    httpOnly: true,
    path: "/",
    maxAge: 0,
  });
  return result;
}
