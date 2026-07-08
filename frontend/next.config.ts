import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

function imageRemotePatterns(): NonNullable<NextConfig["images"]>["remotePatterns"] {
  const patterns: NonNullable<NextConfig["images"]>["remotePatterns"] = [
    { protocol: "http", hostname: "localhost", port: "8000", pathname: "/**" },
    { protocol: "http", hostname: "127.0.0.1", port: "8000", pathname: "/**" },
  ];

  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (apiBaseUrl) {
    try {
      const url = new URL(apiBaseUrl);
      const alreadyAllowed = patterns.some(
        (p) =>
          p.protocol === url.protocol.replace(":", "") &&
          p.hostname === url.hostname &&
          (p.port ?? "") === url.port,
      );
      if (!alreadyAllowed && (url.protocol === "http:" || url.protocol === "https:")) {
        patterns.push({
          protocol: url.protocol.replace(":", "") as "http" | "https",
          hostname: url.hostname,
          port: url.port,
          pathname: "/**",
        });
      }
    } catch {
      // Ignore malformed local env; Next will still use the fixed local patterns.
    }
  }

  return patterns;
}

// Backend origin for server-side proxy rewrites.
// NEXT_PUBLIC_API_URL is the raw backend base (no /api/v1 suffix).
// Falls back to the dev default so the rewrite works even without .env.
const backendOrigin = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Hide the framework's dev-tools indicator (the small Next.js "N" logo button
  // that renders bottom-left only under `next dev`). It is a dev-only overlay,
  // never present in production builds, but the owner wants a clean marketplace
  // surface with no stray floating element in any environment/screenshot.
  devIndicators: false,
  images: {
    remotePatterns: imageRemotePatterns(),
  },
  // Proxy /api/v1/* → backend so the httpOnly refresh cookie is same-origin.
  // Without this, the frontend (localhost:3000) would set the cookie for
  // localhost:8000, causing cross-port cookie inconsistencies in some browsers
  // and preventing token refresh from working reliably.
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${backendOrigin}/api/v1/:path*`,
      },
    ];
  },
  // Build-only: size the build/static-generation worker pool by available memory
  // so page-data collection workers don't starve/OOM under memory pressure (which
  // otherwise surfaces as flaky "Cannot find module for page" build failures).
  // Runtime behaviour is unaffected.
  experimental: {
    memoryBasedWorkersCount: true,
  },
};

export default withNextIntl(nextConfig);
