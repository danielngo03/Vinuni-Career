"use client";

import {
  ArrowRight,
  BookmarkSimple,
  Briefcase,
  CalendarDots,
  CheckCircle,
  FileText,
  Robot,
} from "@phosphor-icons/react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { apiFetch, apiMessage } from "@/lib/api/client";
import type { StudentDashboard } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { MetricStrip } from "@/components/dashboard/metric-strip";
import { RingScore } from "@/components/dashboard/ring-score";
import { StatusBadge } from "@/components/dashboard/status-badge";
import { WorkspaceHero } from "@/components/dashboard/workspace-hero";

export function StudentDashboardScreen({
  data,
  locale,
}: {
  data: StudentDashboard;
  locale: string;
}) {
  const { dictionary } = useI18n();
  const [workingId, setWorkingId] = useState<string | null>(null);
  const primaryCv = data.cvs.find((cv) => cv.is_primary) || data.cvs[0];
  const readiness = primaryCv
    ? Math.min(96, 60 + (primaryCv.skills?.length || 0) * 4)
    : 24;
  const base = `/${locale}/student`;

  async function bookmark(jobId: string) {
    setWorkingId(jobId);
    try {
      await apiFetch(`/jobs/${jobId}/bookmarks`, { method: "POST" });
      toast.success(dictionary.jobs.saved);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setWorkingId(null);
    }
  }

  return (
    <div className="mx-auto max-w-[1500px] space-y-5 p-4 md:p-6">
      <WorkspaceHero
        eyebrow={data.identity.org_name}
        title={dictionary.operations.student.jobsTitle}
        description={dictionary.operations.student.jobsDescription}
        action={dictionary.ai.careerCoaching}
        actionHref={`${base}/ai`}
      />
      <MetricStrip
        metrics={data.metrics.map((metric, index) => ({
          ...metric,
          label: dictionary.metrics.student[index] || metric.label,
        }))}
      />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-5">
          <section className="overflow-hidden rounded-2xl border bg-white">
            <SectionHeader
              icon={Briefcase}
              title={dictionary.operations.student.jobsTitle}
              description={dictionary.operations.student.jobsDescription}
              href={`${base}/jobs`}
              action={dictionary.common.viewAll}
            />
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="border-b bg-slate-50 text-[11px] font-bold uppercase tracking-wide text-muted">
                  <tr>
                    <th className="px-5 py-3">{dictionary.forms.title}</th>
                    <th className="px-5 py-3">{dictionary.jobs.company}</th>
                    <th className="px-5 py-3">Match</th>
                    <th className="px-5 py-3">{dictionary.jobs.skills}</th>
                    <th className="px-5 py-3 text-right">{dictionary.common.actions}</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {data.recommended_jobs.slice(0, 5).map((job) => (
                    <tr key={job.id} className="hover:bg-blue-50/35">
                      <td className="px-5 py-4">
                        <p className="font-semibold">{job.title}</p>
                        <p className="mt-1 text-xs text-muted">
                          {job.location || dictionary.common.unknown}
                        </p>
                      </td>
                      <td className="px-5 py-4 font-medium">{job.company}</td>
                      <td className="px-5 py-4">
                        <div className="w-28">
                          <span className="text-xs font-semibold text-success">
                            {Math.round(job.match_score || 0)}%
                          </span>
                          <Progress
                            value={job.match_score || 0}
                            indicatorClassName="mt-1 bg-success"
                          />
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex max-w-52 flex-wrap gap-1">
                          {(job.tags || []).slice(0, 3).map((tag) => (
                            <Badge key={tag} tone="blue">
                              {tag}
                            </Badge>
                          ))}
                        </div>
                      </td>
                      <td className="px-5 py-4 text-right">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => bookmark(job.id)}
                          disabled={workingId === job.id}
                          aria-label={dictionary.jobs.save}
                        >
                          <BookmarkSimple className="size-4" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-2xl border bg-white p-5">
            <SectionHeader
              inline
              icon={CalendarDots}
              title={dictionary.operations.student.eventsTitle}
              description={dictionary.operations.student.eventsDescription}
              href={`${base}/events`}
              action={dictionary.common.viewAll}
            />
            <div className="mt-5 grid gap-3 md:grid-cols-3">
              {(data.events || []).slice(0, 3).map((event) => (
                <article
                  key={event.id}
                  className="rounded-2xl border p-4 transition-all hover:-translate-y-0.5 hover:border-blue-200"
                >
                  <CalendarDots className="size-5 text-primary" weight="duotone" />
                  <p className="mt-4 font-semibold">{event.title}</p>
                  <p className="mt-2 text-xs leading-5 text-muted">
                    {new Intl.DateTimeFormat(locale, {
                      dateStyle: "medium",
                      timeStyle: "short",
                    }).format(new Date(event.start_time))}
                  </p>
                  <p className="mt-1 text-xs text-muted">{event.location}</p>
                </article>
              ))}
            </div>
          </section>
        </div>

        <aside className="space-y-5">
          <section className="rounded-2xl border bg-white p-5">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold">{dictionary.sections.cv}</h2>
              <Link
                href={`${base}/cv`}
                className="focus-ring rounded text-xs font-semibold text-primary hover:underline"
              >
                {dictionary.common.details}
              </Link>
            </div>
            <div className="mt-5">
              <RingScore
                value={readiness}
                label={dictionary.sections.cv}
                description={dictionary.metrics.profileUpdated}
              />
            </div>
            <div className="mt-5 space-y-2.5">
              {[
                [dictionary.forms.description, Boolean(primaryCv?.masked_preview)],
                [dictionary.jobs.skills, Boolean(primaryCv?.skills?.length)],
                [dictionary.sections.documents, Boolean(primaryCv)],
              ].map(([label, done]) => (
                <div key={String(label)} className="flex items-center gap-2 text-sm">
                  <CheckCircle
                    className={done ? "text-success" : "text-slate-300"}
                    weight={done ? "fill" : "regular"}
                  />
                  <span className={done ? "text-foreground" : "text-muted"}>
                    {String(label)}
                  </span>
                </div>
              ))}
            </div>
            <Button className="mt-5 w-full" asChild>
              <Link href={`${base}/cv`}>
                <FileText className="size-4" />
                {dictionary.ai.cvExtraction}
              </Link>
            </Button>
          </section>

          <section className="rounded-2xl border bg-white p-5">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold">{dictionary.sections.applications}</h2>
              <Link
                href={`${base}/applications`}
                className="text-xs font-semibold text-primary"
              >
                {dictionary.common.viewAll}
              </Link>
            </div>
            <div className="mt-4 space-y-4">
              {data.applications.slice(0, 4).map((application) => (
                <div
                  key={application.id}
                  className="border-l-2 border-blue-100 pl-3"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold">
                        {application.job_title}
                      </p>
                      <p className="mt-1 text-xs text-muted">
                        {application.company}
                      </p>
                    </div>
                    <StatusBadge status={application.status} />
                  </div>
                </div>
              ))}
            </div>
          </section>

          <Link
            href={`${base}/ai`}
            className="focus-ring block rounded-2xl border border-blue-100 bg-blue-50/70 p-5 transition-colors hover:bg-blue-50"
          >
            <Robot className="size-6 text-primary" weight="duotone" />
            <h2 className="mt-4 font-semibold">{dictionary.ai.title}</h2>
            <p className="mt-2 text-sm leading-6 text-muted">
              {dictionary.ai.description}
            </p>
            <span className="mt-4 flex items-center gap-2 text-sm font-semibold text-primary">
              {dictionary.ai.start}
              <ArrowRight className="size-4" />
            </span>
          </Link>
        </aside>
      </div>
    </div>
  );
}

function SectionHeader({
  icon: Icon,
  title,
  description,
  href,
  action,
  inline = false,
}: {
  icon: typeof Briefcase;
  title: string;
  description: string;
  href: string;
  action: string;
  inline?: boolean;
}) {
  return (
    <div className={inline ? "" : "border-b p-5"}>
      <div className="flex items-start gap-3">
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
    </div>
  );
}
