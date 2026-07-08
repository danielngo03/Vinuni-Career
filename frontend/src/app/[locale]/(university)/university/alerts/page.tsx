import { redirect } from "@/i18n/navigation";

/** Legacy path → Platform Admin console `/admin/alerts`. */
export default async function LegacyAlertsRedirect({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  redirect({ href: "/admin/alerts", locale });
}
