import { redirect } from "@/i18n/navigation";

/** Legacy path → Platform Admin console `/admin/logs`. */
export default async function LegacyLogsRedirect({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  redirect({ href: "/admin/logs", locale });
}
