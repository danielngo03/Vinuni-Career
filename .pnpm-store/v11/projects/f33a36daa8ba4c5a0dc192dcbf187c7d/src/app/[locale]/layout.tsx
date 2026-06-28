import { notFound } from "next/navigation";
import { isLocale, type Locale } from "@/lib/i18n/config";
import { getDictionary } from "@/lib/i18n/dictionaries";
import { I18nProvider } from "@/lib/i18n/provider";

export function generateStaticParams() {
  return [{ locale: "vi" }, { locale: "en" }];
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  const safeLocale = locale satisfies Locale;
  return (
    <I18nProvider locale={safeLocale} dictionary={getDictionary(safeLocale)}>
      <div data-locale={safeLocale}>{children}</div>
    </I18nProvider>
  );
}
