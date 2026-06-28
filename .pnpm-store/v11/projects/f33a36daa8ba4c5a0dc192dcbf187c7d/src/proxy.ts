import { NextRequest, NextResponse } from "next/server";
import { defaultLocale, isLocale } from "@/lib/i18n/config";

const publicFiles = /\.(.*)$/;
const workspaceByHost: Record<string, string> = {
  student: "student",
  partner: "partner",
  uni: "university",
};

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname.startsWith("/favicon") ||
    publicFiles.test(pathname)
  ) {
    return NextResponse.next();
  }

  const host = (request.headers.get("host") || "").split(":")[0];
  const appDomain = process.env.NEXT_PUBLIC_APP_DOMAIN || "example.com";
  if (host === `www.${appDomain}`) {
    const url = request.nextUrl.clone();
    url.host = appDomain;
    url.protocol = "https";
    return NextResponse.redirect(url, 308);
  }

  const parts = pathname.split("/").filter(Boolean);
  const locale = parts[0] && isLocale(parts[0]) ? parts[0] : defaultLocale;
  const normalizedPath = parts[0] && isLocale(parts[0]) ? pathname : `/${locale}${pathname}`;
  const subdomain = host.endsWith(`.${appDomain}`)
    ? host.slice(0, -(appDomain.length + 1))
    : "";
  const workspace = workspaceByHost[subdomain];

  if (workspace) {
    const workspacePrefix = `/${locale}/${workspace}`;
    const destination =
      normalizedPath === `/${locale}` || normalizedPath === `/${locale}/`
        ? workspacePrefix
        : normalizedPath.startsWith(workspacePrefix)
          ? normalizedPath
          : `${workspacePrefix}${normalizedPath.slice(locale.length + 1)}`;
    const url = request.nextUrl.clone();
    url.pathname = destination;
    return NextResponse.rewrite(url);
  }

  if (normalizedPath !== pathname) {
    const url = request.nextUrl.clone();
    url.pathname = normalizedPath;
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image).*)"],
};
