import { redirect } from "@/i18n/navigation";

/** Legacy path → Platform Admin console `/admin/ai-distribution`. */
export default async function LegacyAiDistributionRedirect({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  redirect({ href: "/admin/ai-distribution", locale });
}
