import { redirect } from "@/i18n/navigation";

/** Legacy path → Platform Admin console `/admin/analytics`. */
export default async function LegacyAnalyticsRedirect({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  redirect({ href: "/admin/analytics", locale });
}
