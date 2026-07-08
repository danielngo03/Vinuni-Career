import { redirect } from "@/i18n/navigation";

/** Legacy path → Platform Admin console `/admin/audit-log`. */
export default async function LegacyAuditLogRedirect({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  redirect({ href: "/admin/audit-log", locale });
}
