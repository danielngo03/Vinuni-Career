import { getTranslations } from "next-intl/server";
import type { Icon } from "@phosphor-icons/react";
import { EmptyState } from "@/components/ui";

/** Honest under-construction state for public routes shipping in later phases. */
export async function PublicPlaceholder({
  title,
  icon,
}: {
  title: string;
  icon: Icon;
}) {
  const t = await getTranslations("shell");
  return (
    <div className="mx-auto max-w-[1280px] px-4 py-12 lg:px-6">
      <h1 className="mb-6 text-2xl font-bold tracking-tight text-[var(--text-primary)]">
        {title}
      </h1>
      <EmptyState
        kind="empty"
        icon={icon}
        title={t("comingSoonTitle")}
        description={t("comingSoonBody")}
      />
    </div>
  );
}
