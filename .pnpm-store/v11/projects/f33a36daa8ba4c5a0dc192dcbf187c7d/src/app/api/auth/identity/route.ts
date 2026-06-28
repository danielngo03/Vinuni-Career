import { NextResponse } from "next/server";
import type { Identity } from "@/lib/api/types";
import {
  ACCESS_COOKIE,
  IDENTITY_COOKIE,
  PORTAL_COOKIE,
  sessionCookieOptions,
} from "@/lib/auth/cookies";

const API_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000/api/v1";

export async function POST(request: Request) {
  const { identity_id } = (await request.json()) as { identity_id?: string };
  const token = request.headers
    .get("cookie")
    ?.match(new RegExp(`${ACCESS_COOKIE}=([^;]+)`))?.[1];
  if (!token || !identity_id) {
    return NextResponse.json({ detail: "Invalid identity selection" }, { status: 400 });
  }
  const response = await fetch(`${API_URL}/auth/identity`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${decodeURIComponent(token)}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ identity_id }),
    cache: "no-store",
  });
  const body = await response.json();
  if (!response.ok) return NextResponse.json(body, { status: response.status });

  const identity = body as Identity;
  const result = NextResponse.json(identity);
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
  return result;
}
