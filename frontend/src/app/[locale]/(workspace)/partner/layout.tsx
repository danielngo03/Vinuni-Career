import { WorkspaceGuard } from "@/components/layouts/workspace-guard";
import { isLocale, type Locale } from "@/lib/i18n/config";

export default async function PartnerLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale: rawLocale } = await params;
  const locale: Locale = isLocale(rawLocale) ? rawLocale : "vi";
  return (
    <WorkspaceGuard locale={locale} portal="partner">
      {children}
    </WorkspaceGuard>
  );
}
