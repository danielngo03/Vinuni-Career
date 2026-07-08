import { redirect } from "@/i18n/navigation";

/**
 * Legacy path — the Platform Admin console was split into its own `/admin/*`
 * route group (owner decision 2026-07-08). Redirect old links/bookmarks.
 */
export default async function LegacyPlatformOverviewRedirect({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  redirect({ href: "/admin/platform-overview", locale });
}
