import { getTranslations } from "next-intl/server";

/**
 * Platform admin overview page (`/admin`).
 *
 * Task 16 will replace this with the real `<PlatformOverviewScreen/>`.
 * This placeholder keeps the route functional and typechecks-clean.
 */
export default async function AdminOverviewPage() {
  const t = await getTranslations("adminConsole.page");

  return (
    <div className="space-y-2">
      <h1 className="text-2xl font-bold tracking-tight text-[var(--text-primary)]">
        {t("overviewTitle")}
      </h1>
      <p className="text-sm text-[var(--text-secondary)]">
        {t("overviewSubtitle")}
      </p>
    </div>
  );
}
