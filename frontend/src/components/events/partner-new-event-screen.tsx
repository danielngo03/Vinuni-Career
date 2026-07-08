"use client";

import { useTranslations } from "next-intl";
import { ArrowLeft } from "@phosphor-icons/react";
import { Link, useRouter } from "@/i18n/navigation";
import { PageHeader } from "@/components/layout/page-header";
import { EventForm } from "./event-form";

export function PartnerNewEventScreen() {
  const t = useTranslations("eventsManage");
  const router = useRouter();

  return (
    <>
      <Link
        href="/partner/events"
        className="mb-4 inline-flex items-center gap-1.5 rounded-lg text-sm font-medium text-[var(--text-secondary)] outline-none hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
      >
        <ArrowLeft aria-hidden weight="bold" className="size-4" />
        {t("backToEvents")}
      </Link>
      <PageHeader title={t("newEventTitle")} description={t("newEventSubtitle")} />
      <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-6">
        <EventForm
          mode="create"
          onSuccess={(event) => router.push(`/partner/events/${event.id}`)}
          onCancel={() => router.push("/partner/events")}
        />
      </div>
    </>
  );
}
