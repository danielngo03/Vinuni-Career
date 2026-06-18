import { NextResponse } from "next/server";
import {
  ACCESS_COOKIE,
  IDENTITY_COOKIE,
  PORTAL_COOKIE,
  REFRESH_COOKIE,
  sessionCookieOptions,
} from "@/lib/auth/cookies";

const API_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000/api/v1";

export async function POST(request: Request) {
  const refresh = request.headers
    .get("cookie")
    ?.match(new RegExp(`${REFRESH_COOKIE}=([^;]+)`))?.[1];
  if (refresh) {
    await fetch(`${API_URL}/auth/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: decodeURIComponent(refresh) }),
    }).catch(() => undefined);
  }
  const response = NextResponse.json({ message: "Signed out" });
  for (const name of [
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    IDENTITY_COOKIE,
    PORTAL_COOKIE,
  ]) {
    response.cookies.set(name, "", sessionCookieOptions(0));
  }
  return response;
}
