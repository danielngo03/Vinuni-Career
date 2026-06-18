"use client";

import {
  Bell,
  Briefcase,
  Buildings,
  CalendarDots,
  ChartBar,
  ChatCircleText,
  ClipboardText,
  FileText,
  FlowArrow,
  Gear,
  Robot,
  ShieldCheck,
  UsersThree,
} from "@phosphor-icons/react";
import Link from "next/link";
import type { Portal } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/provider";
import { AIOperations } from "@/features/ai/ai-operations";
import { ApplicationCenter } from "@/features/applications/application-center";
import { CVCenter } from "@/features/cv/cv-center";
import { EventCenter, ReviewCenter } from "@/features/events/event-center";
import { JobCenter } from "@/features/jobs/job-center";
import {
  CandidateCenter,
  PartnerAnalytics,
  PartnerInterviewCenter,
} from "@/features/partner/recruitment-center";
import {
  ModerationCenter,
  PartnerDirectory,
  RegistrationCenter,
  UniversityAnalytics,
  WorkflowCenter,
} from "@/features/university/governance-center";
import { Button } from "@/components/ui/button";
import { PageHeading } from "@/components/ui/page-heading";

const icons = {
  jobs: Briefcase,
  cv: FileText,
  applications: ClipboardText,
  interviews: ChatCircleText,
  events: CalendarDots,
  reviews: Buildings,
  candidates: UsersThree,
  analytics: ChartBar,
  registrations: ClipboardText,
  moderation: ShieldCheck,
  partners: Buildings,
  workflows: FlowArrow,
  ai: Robot,
  notifications: Bell,
  settings: Gear,
} as const;

export function PortalSection({
  portal,
  section,
  orgId,
}: {
  portal: Portal;
  section: string;
  orgId?: string | null;
}) {
  const { locale, dictionary } = useI18n();
  const Icon = icons[section as keyof typeof icons] || Briefcase;
  const copy = sectionCopy(portal, section, dictionary);

  return (
    <div className="mx-auto max-w-[1500px] space-y-5 p-4 md:p-6">
      <PageHeading
        icon={Icon}
        eyebrow={dictionary.shell.workspace}
        title={copy.title}
        description={copy.description}
        actions={
          <Button variant="outline" asChild>
            <Link href={`/${locale}/${portal}`}>
              {dictionary.common.backToOverview}
            </Link>
          </Button>
        }
      />
      {renderSection(portal, section, orgId)}
    </div>
  );
}

function renderSection(portal: Portal, section: string, orgId?: string | null) {
  if (section === "ai") return <AIOperations />;
  if (portal === "student") {
    if (section === "jobs") return <JobCenter portal="student" />;
    if (section === "cv") return <CVCenter />;
    if (section === "applications") return <ApplicationCenter />;
    if (section === "interviews") return <ApplicationCenter showOnlyInterviews />;
    if (section === "events") return <EventCenter />;
    if (section === "reviews") return <ReviewCenter />;
  }
  if (portal === "partner") {
    if (section === "jobs") return <JobCenter portal="partner" orgId={orgId} />;
    if (section === "candidates") return <CandidateCenter />;
    if (section === "interviews") return <PartnerInterviewCenter />;
    if (section === "analytics") return <PartnerAnalytics />;
  }
  if (portal === "university") {
    if (section === "registrations") return <RegistrationCenter />;
    if (section === "moderation") return <ModerationCenter />;
    if (section === "partners") return <PartnerDirectory />;
    if (section === "workflows") return <WorkflowCenter />;
    if (section === "analytics") return <UniversityAnalytics />;
  }
  return <SettingsPanel />;
}

function SettingsPanel() {
  const { dictionary } = useI18n();
  return (
    <section className="rounded-2xl border bg-white p-5">
      <div className="flex items-center gap-3">
        <Gear className="size-6 text-primary" weight="duotone" />
        <div>
          <h2 className="font-semibold">{dictionary.nav.settings}</h2>
          <p className="mt-1 text-sm text-muted">
            {dictionary.common.language}: {dictionary.brand}
          </p>
        </div>
      </div>
    </section>
  );
}

function sectionCopy(
  portal: Portal,
  section: string,
  dictionary: ReturnType<typeof useI18n>["dictionary"],
) {
  const fallback = {
    title:
      dictionary.sections[section as keyof typeof dictionary.sections] ||
      dictionary.shell.workspace,
    description: dictionary.shell.searchHint,
  };
  if (portal === "student") {
    const map = {
      jobs: [dictionary.operations.student.jobsTitle, dictionary.operations.student.jobsDescription],
      cv: [dictionary.operations.student.cvTitle, dictionary.operations.student.cvDescription],
      applications: [
        dictionary.operations.student.applicationsTitle,
        dictionary.operations.student.applicationsDescription,
      ],
      interviews: [
        dictionary.sections.interviews,
        dictionary.operations.student.applicationsDescription,
      ],
      events: [
        dictionary.operations.student.eventsTitle,
        dictionary.operations.student.eventsDescription,
      ],
      reviews: [
        dictionary.operations.student.reviewsTitle,
        dictionary.operations.student.reviewsDescription,
      ],
      ai: [dictionary.ai.title, dictionary.ai.description],
    } as const;
    const value = map[section as keyof typeof map];
    return value ? { title: value[0], description: value[1] } : fallback;
  }
  if (portal === "partner") {
    const map = {
      jobs: [dictionary.operations.partner.jobsTitle, dictionary.operations.partner.jobsDescription],
      candidates: [
        dictionary.operations.partner.candidatesTitle,
        dictionary.operations.partner.candidatesDescription,
      ],
      interviews: [
        dictionary.operations.partner.interviewsTitle,
        dictionary.operations.partner.interviewsDescription,
      ],
      analytics: [
        dictionary.operations.partner.analyticsTitle,
        dictionary.operations.partner.analyticsDescription,
      ],
      ai: [dictionary.ai.title, dictionary.ai.description],
    } as const;
    const value = map[section as keyof typeof map];
    return value ? { title: value[0], description: value[1] } : fallback;
  }
  const map = {
    registrations: [
      dictionary.operations.university.registrationsTitle,
      dictionary.operations.university.registrationsDescription,
    ],
    moderation: [
      dictionary.operations.university.moderationTitle,
      dictionary.operations.university.moderationDescription,
    ],
    partners: [
      dictionary.operations.university.partnersTitle,
      dictionary.operations.university.partnersDescription,
    ],
    workflows: [
      dictionary.operations.university.workflowsTitle,
      dictionary.operations.university.workflowsDescription,
    ],
    analytics: [
      dictionary.operations.university.analyticsTitle,
      dictionary.operations.university.analyticsDescription,
    ],
    ai: [dictionary.ai.title, dictionary.ai.description],
  } as const;
  const value = map[section as keyof typeof map];
  return value ? { title: value[0], description: value[1] } : fallback;
}
