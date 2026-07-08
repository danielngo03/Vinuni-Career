import { redirect } from "@/i18n/navigation";

/**
 * Legacy path — university "Users" was a superadmin platform-wide user list
 * (backed by the admin users API) that duplicated the richer Users & Access
 * console. It has been folded into the Platform Admin console (owner decision
 * 2026-07-08). The `UniversityUsersScreen` component is retained but no longer
 * routed; org-scoped staff management lives at `/university/team`.
 */
export default async function LegacyUniversityUsersRedirect({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  redirect({ href: "/admin/access", locale });
}
