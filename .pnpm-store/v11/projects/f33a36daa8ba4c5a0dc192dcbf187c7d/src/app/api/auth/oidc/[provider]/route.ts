import { NextResponse } from "next/server";

const API_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000/api/v1";

export async function GET(
  request: Request,
  context: { params: Promise<{ provider: string }> },
) {
  const { provider } = await context.params;
  const locale = new URL(request.url).searchParams.get("locale") || "vi";
  const response = NextResponse.redirect(
    `${API_URL}/auth/oidc/${encodeURIComponent(provider)}/authorize`,
  );
  response.cookies.set("vinuni_oidc_locale", locale, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 600,
  });
  return response;
}
