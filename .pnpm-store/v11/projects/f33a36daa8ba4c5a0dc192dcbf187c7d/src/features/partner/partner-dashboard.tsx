"use client";

import {
  ArrowRight,
  Briefcase,
  ChartBar,
  Check,
  Robot,
  UsersThree,
} from "@phosphor-icons/react";
import Link from "next/link";
import type { PartnerDashboard } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { MetricStrip } from "@/components/dashboard/metric-strip";
import { StatusBadge } from "@/components/dashboard/status-badge";
import { WorkspaceHero } from "@/components/dashboard/workspace-hero";

const stages = ["APPLIED", "SHORTLISTED", "HR_INTERVIEW", "OFFERED"];

export function PartnerDashboardScreen({
  data,
  locale,
}: {
  data: PartnerDashboard;
  locale: string;
}) {
  const { dictionary } = useI18n();
  const base = `/${locale}/partner`;
  const total = Math.max(
    1,
    (data.application_distribution || []).reduce((sum, item) => sum + item.value, 0),
  );
  return (
    <div className="mx-auto max-w-[1500px] space-y-5 p-4 md:p-6">
      <WorkspaceHero
        eyebrow={data.identity.org_name}
        title={dictionary.operations.partner.jobsTitle}
        description={dictionary.operations.partner.jobsDescription}
        action={dictionary.ai.profileMatching}
        actionHref={`${base}/ai`}
      />
      <MetricStrip
        metrics={data.metrics.map((metric, index) => ({
          ...metric,
          label: dictionary.metrics.partner[index] || metric.label,
        }))}
      />

      <section className="overflow-hidden rounded-2xl border bg-white">
        <OverviewHeader
          icon={Briefcase}
          title={dictionary.operations.partner.jobsTitle}
          description={dictionary.operations.partner.jobsDescription}
          href={`${base}/jobs`}
          action={dictionary.common.viewAll}
        />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="border-b bg-slate-50 text-[11px] font-bold uppercase tracking-wide text-muted">
              <tr>
                <th className="px-5 py-3">{dictionary.forms.title}</th>
                <th className="px-5 py-3">{dictionary.common.status}</th>
                <th className="px-5 py-3">{dictionary.jobs.location}</th>
                <th className="px-5 py-3">{dictionary.jobs.skills}</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {data.jobs.slice(0, 6).map((job) => (
                <tr key={job.id} className="hover:bg-blue-50/30">
                  <td className="px-5 py-4">
                    <p className="font-semibold">{job.title}</p>
                    <p className="mt-1 text-xs text-muted">{job.company}</p>
                  </td>
                  <td className="px-5 py-4">
                    <StatusBadge status={job.status} />
                  </td>
                  <td className="px-5 py-4 text-muted">
                    {job.location || dictionary.common.unknown}
                  </td>
                  <td className="px-5 py-4">
                    <div className="flex flex-wrap gap-1">
                      {(job.tags || []).slice(0, 3).map((tag) => (
                        <Badge key={tag} tone="blue">
                          {tag}
                        </Badge>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-2xl border bg-white">
        <OverviewHeader
          icon={UsersThree}
          title={dictionary.operations.partner.candidatesTitle}
          description={dictionary.operations.partner.candidatesDescription}
          href={`${base}/candidates`}
          action={dictionary.common.open}
        />
        <div className="overflow-x-auto p-4 sm:p-5">
          <div className="flex min-w-max gap-3">
            {stages.map((stage) => {
              const candidates = data.candidates.filter(
                (candidate) => candidate.status === stage,
              );
              return (
                <div key={stage} className="w-[265px] rounded-2xl bg-slate-50 p-3">
                  <div className="flex items-center justify-between px-1">
                    <p className="text-xs font-bold uppercase tracking-wide text-slate-600">
                      {stage.replaceAll("_", " ")}
                    </p>
                    <Badge tone="gray">{candidates.length}</Badge>
                  </div>
                  <div className="mt-3 space-y-3">
                    {candidates.slice(0, 3).map((candidate) => (
                      <article
                        key={candidate.application_id}
                        className="rounded-2xl border bg-white p-4"
                      >
                        <p className="font-semibold">{candidate.anonymous_label}</p>
                        <p className="mt-1 truncate text-xs text-muted">
                          {candidate.job_title}
                        </p>
                        <div className="mt-4 flex items-center gap-2">
                          <Badge
                            tone={candidate.consent_to_unmask ? "green" : "gray"}
                          >
                            {candidate.consent_to_unmask ? (
                              <Check className="mr-1 size-3" />
                            ) : null}
                            {Math.round(candidate.ai_match_score || 0)}%
                          </Badge>
                        </div>
                      </article>
                    ))}
                    {!candidates.length ? (
                      <div className="rounded-xl border border-dashed bg-white p-5 text-center text-xs text-muted">
                        {dictionary.common.empty}
                      </div>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <section className="rounded-2xl border bg-white p-5">
          <div className="flex items-center gap-2">
            <ChartBar className="size-5 text-primary" weight="duotone" />
            <h2 className="font-semibold">{dictionary.sections.analytics}</h2>
          </div>
          <div className="mt-5 space-y-4">
            {(data.application_distribution || []).map((point) => (
              <div key={point.label}>
                <div className="mb-1.5 flex justify-between text-sm">
                  <span>{point.label.replaceAll("_", " ")}</span>
                  <span className="font-semibold">{point.value}</span>
                </div>
                <Progress value={(point.value / total) * 100} />
              </div>
            ))}
          </div>
        </section>
        <Link
          href={`${base}/ai`}
          className="focus-ring rounded-2xl border border-blue-100 bg-blue-50/70 p-5 transition-colors hover:bg-blue-50"
        >
          <Robot className="size-6 text-primary" weight="duotone" />
          <h2 className="mt-4 font-semibold">{dictionary.ai.title}</h2>
          <p className="mt-2 text-sm leading-6 text-muted">
            {dictionary.ai.description}
          </p>
          <span className="mt-5 flex items-center gap-2 text-sm font-semibold text-primary">
            {dictionary.ai.start}
            <ArrowRight className="size-4" />
          </span>
        </Link>
      </div>
    </div>
  );
}

function OverviewHeader({
  icon: Icon,
  title,
  description,
  href,
  action,
}: {
  icon: typeof Briefcase;
  title: string;
  description: string;
  href: string;
  action: string;
}) {
  return (
    <div className="flex items-start gap-3 border-b p-5">
      <Icon className="mt-0.5 size-5 text-primary" weight="duotone" />
      <div>
        <h2 className="font-semibold">{title}</h2>
        <p className="mt-1 text-sm text-muted">{description}</p>
      </div>
      <Button variant="ghost" size="sm" className="ml-auto" asChild>
        <Link href={href}>
          {action}
          <ArrowRight className="size-4" />
        </Link>
      </Button>
    </div>
  );
}
