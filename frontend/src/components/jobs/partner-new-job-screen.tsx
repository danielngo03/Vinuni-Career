"use client";

import { useTranslations } from "next-intl";
import { ArrowLeft } from "@phosphor-icons/react";
import { Link, useRouter } from "@/i18n/navigation";
import { PageHeader } from "@/components/layout/page-header";
import { JobForm } from "./job-form";

export function PartnerNewJobScreen() {
  const t = useTranslations("jobs");
  const router = useRouter();

  return (
    <>
      <Link
        href="/partner/jobs"
        className="mb-4 inline-flex items-center gap-1.5 rounded-lg text-sm font-medium text-[var(--text-secondary)] outline-none hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
      >
        <ArrowLeft aria-hidden weight="bold" className="size-4" />
        {t("backToJobs")}
      </Link>
      <PageHeader title={t("newJobTitle")} description={t("newJobSubtitle")} />
      <div className="rounded-2xl border border-[var(--border-default)] bg-white p-6">
        <JobForm
          mode="create"
          onSuccess={(job) => router.push(`/partner/jobs/${job.id}`)}
          onCancel={() => router.push("/partner/jobs")}
        />
      </div>
    </>
  );
}
