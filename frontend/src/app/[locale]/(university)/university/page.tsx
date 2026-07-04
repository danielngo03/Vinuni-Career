import { redirect } from "@/i18n/navigation";

export default async function UniversityIndex({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  redirect({ href: "/university/dashboard", locale });
}
