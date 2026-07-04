import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { NextIntlClientProvider } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { routing, type AppLocale } from "@/i18n/routing";
import { Providers } from "@/components/providers";
import { DocumentTitle } from "@/components/layout/document-title";
import { APP_BRAND_NAME } from "@/lib/route-titles";
import "../globals.css";

export const metadata: Metadata = {
  title: {
    default: APP_BRAND_NAME,
    template: `%s | ${APP_BRAND_NAME}`,
  },
  applicationName: APP_BRAND_NAME,
  description:
    "Nền tảng nghề nghiệp của VinUniversity — việc làm, sự kiện, cố vấn và CV Studio.",
  icons: {
    icon: [
      {
        url: "/brand/logo-dark.png",
        media: "(prefers-color-scheme: light)",
        type: "image/png",
      },
      {
        url: "/brand/logo-light.png",
        media: "(prefers-color-scheme: dark)",
        type: "image/png",
      },
    ],
  },
};

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

async function getActiveFontFamily(): Promise<string | null> {
  try {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const res = await fetch(`${apiUrl}/api/v1/platform-settings`, {
      next: { revalidate: 300 },
    });
    if (!res.ok) return null;
    const json = await res.json();
    const family: string | undefined = json?.data?.font_family;
    return family && family !== "Plus Jakarta Sans" ? family : null;
  } catch {
    return null;
  }
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;

  if (!routing.locales.includes(locale as AppLocale)) {
    notFound();
  }

  setRequestLocale(locale);
  const [messages, overrideFamily] = await Promise.all([
    getMessages(),
    getActiveFontFamily(),
  ]);

  // Admin font override: write directly to --font-plus-jakarta on <html>.
  // Default is the self-hosted Plus Jakarta Sans declared in globals.css.
  const fontOverride = overrideFamily
    ? ({ "--font-plus-jakarta": `'${overrideFamily}', sans-serif` } as React.CSSProperties)
    : undefined;

  return (
    <html lang={locale} data-theme="light" style={fontOverride}>
      <head>
        {/* Anti-FOUC: reads the saved theme preference and applies it before
            the first paint so dark-mode users never see a light flash. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('vinuni-theme');var d=t==='dark'||(t==='system'&&matchMedia('(prefers-color-scheme: dark)').matches)?'dark':'light';document.documentElement.dataset.theme=d;}catch(e){}})();`,
          }}
        />
        {/* Preload Plus Jakarta Sans Latin+Vietnamese for fast override rendering
            when the admin selects it via platform-settings. */}
        <link
          rel="preload"
          href="/fonts/plus-jakarta-sans-latin.woff2"
          as="font"
          type="font/woff2"
          crossOrigin="anonymous"
        />
        <link
          rel="preload"
          href="/fonts/plus-jakarta-sans-vietnamese.woff2"
          as="font"
          type="font/woff2"
          crossOrigin="anonymous"
        />
        <link
          rel="icon"
          href="/brand/logo-dark.png"
          type="image/png"
          media="(prefers-color-scheme: light)"
        />
        <link
          rel="icon"
          href="/brand/logo-light.png"
          type="image/png"
          media="(prefers-color-scheme: dark)"
        />
      </head>
      <body className="font-sans antialiased" suppressHydrationWarning>
        <NextIntlClientProvider messages={messages}>
          <DocumentTitle />
          <Providers>{children}</Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
