import { redirect } from "@/i18n/navigation";

/** `/admin` → the Platform Admin landing (platform overview). */
export default async function AdminIndex({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  redirect({ href: "/admin/platform-overview", locale });
}
