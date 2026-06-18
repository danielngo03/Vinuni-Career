export const ACCESS_COOKIE = "vinuni_access";
export const REFRESH_COOKIE = "vinuni_refresh";
export const IDENTITY_COOKIE = "vinuni_identity";
export const PORTAL_COOKIE = "vinuni_portal";

export function sessionCookieOptions(maxAge: number) {
  const domain = process.env.SESSION_COOKIE_DOMAIN || undefined;
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge,
    ...(domain ? { domain } : {}),
  };
}
