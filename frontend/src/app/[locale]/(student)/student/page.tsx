import { redirect } from "@/i18n/navigation";

export default async function StudentIndex({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  redirect({ href: "/student/dashboard", locale });
}
