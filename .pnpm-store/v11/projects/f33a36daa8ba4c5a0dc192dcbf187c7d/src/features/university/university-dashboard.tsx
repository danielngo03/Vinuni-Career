"use client";

import {
  ArrowRight,
  Buildings,
  ClipboardText,
  Robot,
  ShieldCheck,
} from "@phosphor-icons/react";
import Link from "next/link";
import type {
  RegistrationQueueItem,
  UniversityDashboard,
  VerificationPolicy,
} from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MetricStrip } from "@/components/dashboard/metric-strip";
import { StatusBadge } from "@/components/dashboard/status-badge";
import { WorkspaceHero } from "@/components/dashboard/workspace-hero";

export function UniversityDashboardScreen({
  data,
  registrations,
  policies,
  locale,
}: {
  data: UniversityDashboard;
  registrations: RegistrationQueueItem[];
  policies: VerificationPolicy[];
  locale: string;
}) {
  const { dictionary } = useI18n();
  const base = `/${locale}/university`;
  const activeRegistrations = registrations.filter(
    (item) => !["APPROVED", "REJECTED", "WITHDRAWN"].includes(item.status),
  );
  return (
    <div className="mx-auto max-w-[1500px] space-y-5 p-4 md:p-6">
      <WorkspaceHero
        eyebrow={data.identity.org_name}
        title={dictionary.operations.university.analyticsTitle}
        description={dictionary.operations.university.analyticsDescription}
        action={dictionary.ai.adminReview}
        actionHref={`${base}/ai`}
      />
      <MetricStrip
        metrics={data.metrics.map((metric, index) => ({
          ...metric,
          label: dictionary.metrics.university[index] || metric.label,
        }))}
      />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-5">
          <section className="rounded-2xl border bg-white">
            <OverviewHeader
              icon={ClipboardText}
              title={dictionary.operations.university.registrationsTitle}
              description={dictionary.operations.university.registrationsDescription}
              href={`${base}/registrations`}
            />
            <div className="divide-y">
              {activeRegistrations.slice(0, 5).map((registration) => (
                <article key={registration.id} className="p-5">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-center">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-semibold">
                          {registration.applicant_name}
                        </h3>
                        <Badge
                          tone={
                            registration.registration_type === "STUDENT"
                              ? "blue"
                              : "cyan"
                          }
                        >
                          {registration.registration_type}
                        </Badge>
                        <StatusBadge status={registration.status} />
                      </div>
                      <p className="mt-1 text-sm text-muted">
                        {registration.applicant_email}
                      </p>
                    </div>
                    <div className="rounded-xl bg-blue-50 px-4 py-3 text-sm">
                      <span className="font-semibold text-primary">
                        {registration.assessment.outcome || "MANUAL_REVIEW"}
                      </span>
                      <span className="ml-2 text-muted">
                        {registration.assessment.confidence || 0}%
                      </span>
                    </div>
                  </div>
                </article>
              ))}
              {!activeRegistrations.length ? (
                <p className="p-8 text-center text-sm text-muted">
                  {dictionary.common.empty}
                </p>
              ) : null}
            </div>
          </section>

          <section className="rounded-2xl border bg-white">
            <OverviewHeader
              icon={ShieldCheck}
              title={dictionary.operations.university.moderationTitle}
              description={dictionary.operations.university.moderationDescription}
              href={`${base}/moderation`}
            />
            <div className="grid gap-3 p-4 sm:p-5 lg:grid-cols-2">
              {data.moderation_queue.slice(0, 4).map((job) => (
                <article key={job.id} className="rounded-2xl border p-4">
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold">{job.title}</h3>
                    <StatusBadge status={job.status} />
                  </div>
                  <p className="mt-2 text-sm text-muted">{job.company}</p>
                  <div className="mt-3 flex flex-wrap gap-1">
                    {(job.tags || []).slice(0, 4).map((tag) => (
                      <Badge key={tag} tone="gray">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          </section>
        </div>

        <aside className="space-y-5">
          <section className="rounded-2xl border bg-white p-5">
            <div className="flex items-center gap-2">
              <Robot className="size-5 text-primary" weight="duotone" />
              <h2 className="font-semibold">{dictionary.ai.title}</h2>
            </div>
            <div className="mt-5 space-y-3">
              {policies.map((policy) => (
                <div key={policy.id} className="rounded-xl bg-slate-50 p-3">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-bold uppercase tracking-wide">
                      {policy.registration_type}
                    </p>
                    <Badge tone={policy.mode === "DISABLED" ? "gray" : "green"}>
                      {policy.mode}
                    </Badge>
                  </div>
                  <p className="mt-2 text-xs text-muted">
                    {policy.model_version} · {policy.confidence_threshold}%
                  </p>
                </div>
              ))}
            </div>
            <Button className="mt-4 w-full" asChild>
              <Link href={`${base}/ai`}>
                {dictionary.ai.start}
                <ArrowRight className="size-4" />
              </Link>
            </Button>
          </section>

          <section className="rounded-2xl border bg-white p-5">
            <div className="flex items-center gap-2">
              <Buildings className="size-5 text-primary" weight="duotone" />
              <h2 className="font-semibold">{dictionary.sections.partners}</h2>
            </div>
            <div className="mt-4 space-y-3">
              {data.partners.slice(0, 5).map((partner) => (
                <div key={partner.id} className="flex items-center gap-3">
                  <div className="flex size-9 items-center justify-center rounded-xl bg-blue-50 text-primary">
                    <Buildings className="size-4" />
                  </div>
                  <p className="min-w-0 flex-1 truncate text-sm font-semibold">
                    {partner.name}
                  </p>
                  <Badge tone={partner.is_verified_partner ? "green" : "amber"}>
                    {partner.is_verified_partner ? "Verified" : "Pending"}
                  </Badge>
                </div>
              ))}
            </div>
            <Button className="mt-4 w-full" variant="outline" asChild>
              <Link href={`${base}/partners`}>{dictionary.common.viewAll}</Link>
            </Button>
          </section>
        </aside>
      </div>
    </div>
  );
}

function OverviewHeader({
  icon: Icon,
  title,
  description,
  href,
}: {
  icon: typeof ClipboardText;
  title: string;
  description: string;
  href: string;
}) {
  const { dictionary } = useI18n();
  return (
    <div className="flex items-start gap-3 border-b p-5">
      <Icon className="mt-0.5 size-5 text-primary" weight="duotone" />
      <div>
        <h2 className="font-semibold">{title}</h2>
        <p className="mt-1 text-sm text-muted">{description}</p>
      </div>
      <Button variant="ghost" size="sm" className="ml-auto" asChild>
        <Link href={href}>
          {dictionary.common.open}
          <ArrowRight className="size-4" />
        </Link>
      </Button>
    </div>
  );
}
