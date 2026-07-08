"use client";

import { useTranslations } from "next-intl";
import { Wrench } from "@phosphor-icons/react";
import { EmptyState } from "@/components/ui";
import { PageHeader } from "./page-header";

/**
 * Honest placeholder for routes whose feature ships in a later phase. This is
 * NOT a fake dashboard: it states the screen is under construction and the
 * shell is ready to wire to real data (CLAUDE.md / UI_QUALITY_BAR.md).
 */
export function ComingSoon({ title }: { title: string }) {
  const t = useTranslations("shell");
  return (
    <>
      <PageHeader title={title} />
      <EmptyState
        kind="empty"
        icon={Wrench}
        title={t("comingSoonTitle")}
        description={t("comingSoonBody")}
      />
    </>
  );
}
