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

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  images: {
    remotePatterns: imageRemotePatterns(),
  },
};

export default withNextIntl(nextConfig);
