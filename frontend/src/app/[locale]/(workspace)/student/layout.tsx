import { isLocale, type Locale } from "@/lib/i18n/config";
import { WorkspaceGuard } from "@/components/layouts/workspace-guard";

export default async function StudentLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale: rawLocale } = await params;
  const locale: Locale = isLocale(rawLocale) ? rawLocale : "vi";
  return (
    <WorkspaceGuard locale={locale} portal="student">
      {children}
    </WorkspaceGuard>
  );
}
