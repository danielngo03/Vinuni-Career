import { redirect } from "@/i18n/navigation";

/** Legacy path → Platform Admin console `/admin/access`. */
export default async function LegacyAccessRedirect({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  redirect({ href: "/admin/access", locale });
}
