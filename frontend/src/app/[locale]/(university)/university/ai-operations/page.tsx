import { redirect } from "@/i18n/navigation";

/** Legacy path → Platform Admin console `/admin/ai-operations`. */
export default async function LegacyAiOperationsRedirect({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  redirect({ href: "/admin/ai-operations", locale });
}
