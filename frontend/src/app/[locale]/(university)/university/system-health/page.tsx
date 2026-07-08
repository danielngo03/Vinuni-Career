import { redirect } from "@/i18n/navigation";

/** Legacy path → Platform Admin console `/admin/system-health`. */
export default async function LegacySystemHealthRedirect({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  redirect({ href: "/admin/system-health", locale });
}
