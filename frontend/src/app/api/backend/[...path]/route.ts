import { NextResponse } from "next/server";
import {
  ACCESS_COOKIE,
  IDENTITY_COOKIE,
  REFRESH_COOKIE,
  sessionCookieOptions,
} from "@/lib/auth/cookies";
import type { TokenResponse } from "@/lib/api/types";

const API_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000/api/v1";

async function proxy(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const incomingUrl = new URL(request.url);
  const cookieHeader = request.headers.get("cookie") || "";
  const access = cookieHeader.match(new RegExp(`${ACCESS_COOKIE}=([^;]+)`))?.[1];
  const refresh = cookieHeader.match(new RegExp(`${REFRESH_COOKIE}=([^;]+)`))?.[1];
  const identity = cookieHeader.match(new RegExp(`${IDENTITY_COOKIE}=([^;]+)`))?.[1];
  if (!access) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  headers.set("Authorization", `Bearer ${decodeURIComponent(access)}`);
  if (identity) headers.set("X-Identity-Id", decodeURIComponent(identity));

  const method = request.method;
  const hasBody = !["GET", "HEAD"].includes(method);
  const requestBody = hasBody ? await request.arrayBuffer() : undefined;
  let response = await fetch(
    `${API_URL}/${path.join("/")}${incomingUrl.search}`,
    {
      method,
      headers,
      body: requestBody,
      cache: "no-store",
    },
  );
  let refreshed: TokenResponse | null = null;
  if (response.status === 401 && refresh) {
    const refreshResponse = await fetch(`${API_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: decodeURIComponent(refresh) }),
      cache: "no-store",
    });
    if (refreshResponse.ok) {
      refreshed = (await refreshResponse.json()) as TokenResponse;
      headers.set("Authorization", `Bearer ${refreshed.access_token}`);
      response = await fetch(
        `${API_URL}/${path.join("/")}${incomingUrl.search}`,
        {
          method,
          headers,
          body: requestBody,
          cache: "no-store",
        },
      );
    }
  }
  const responseHeaders = new Headers();
  const returnedType = response.headers.get("content-type");
  if (returnedType) responseHeaders.set("Content-Type", returnedType);
  const result = new NextResponse(response.body, {
    status: response.status,
    headers: responseHeaders,
  });
  if (refreshed) {
    result.cookies.set(
      ACCESS_COOKIE,
      refreshed.access_token,
      sessionCookieOptions(60 * 60),
    );
    if (refreshed.refresh_token) {
      result.cookies.set(
        REFRESH_COOKIE,
        refreshed.refresh_token,
        sessionCookieOptions(60 * 60 * 24 * 14),
      );
    }
  }
  return result;
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
