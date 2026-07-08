import { redirect } from "@/i18n/navigation";

/** Legacy path → Platform Admin console `/admin/feature-flags`. */
export default async function LegacyFeatureFlagsRedirect({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  redirect({ href: "/admin/feature-flags", locale });
}
