import type { AppLocale } from "@/i18n/routing";

type MessageTree = { [key: string]: string | MessageTree };

function isRecord(value: unknown): value is MessageTree {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function mergeMessages(base: MessageTree, patch: MessageTree): MessageTree {
  const next: MessageTree = { ...base };
  for (const [key, value] of Object.entries(patch)) {
    const current = next[key];
    next[key] =
      isRecord(current) && isRecord(value)
        ? mergeMessages(current, value)
        : value;
  }
  return next;
}

// Message files are split one-per-domain under src/messages/{locale}/{group}/{file}.json
// so each persona/feature area (student, partner, university, public, auth, shared,
// settings) can be edited, reviewed, and diffed independently instead of one shared
// monolith. Namespaces (the top-level key each file exports) must stay 1:1 with the
// `useTranslations("...")` / `getTranslations("...")` call sites in the app; see
// scripts/check-message-parity.mjs for the automated en/vi key-parity gate and
// scripts/messages-manifest.json for the namespace -> file map used to generate this file.
const loaders: Record<AppLocale, Array<() => Promise<{ default: MessageTree }>>> = {
  vi: [
    () => import("./vi/admin/console.json"),
    () => import("./vi/auth/auth.json"),
    () => import("./vi/partner/advertising.json"),
    () => import("./vi/partner/billing.json"),
    () => import("./vi/partner/candidates.json"),
    () => import("./vi/partner/company-profile.json"),
    () => import("./vi/partner/events-manage.json"),
    () => import("./vi/partner/interviews.json"),
    () => import("./vi/partner/offers.json"),
    () => import("./vi/partner/partner-reviews.json"),
    () => import("./vi/partner/pipeline.json"),
    () => import("./vi/partner/reviews.json"),
    () => import("./vi/partner/scorecards.json"),
    () => import("./vi/partner/talent-pool.json"),
    () => import("./vi/partner/team.json"),
    () => import("./vi/public/events.json"),
    () => import("./vi/public/landing.json"),
    () => import("./vi/public/marketplace.json"),
    () => import("./vi/settings/notifications.json"),
    () => import("./vi/settings/settings.json"),
    () => import("./vi/shared/common.json"),
    () => import("./vi/shared/report.json"),
    () => import("./vi/shared/shell.json"),
    () => import("./vi/shared/workflow-builder.json"),
    () => import("./vi/student/ai-assistant.json"),
    () => import("./vi/student/applications.json"),
    () => import("./vi/student/cv.json"),
    () => import("./vi/student/dashboard.json"),
    () => import("./vi/student/feedback.json"),
    () => import("./vi/student/jobs.json"),
    () => import("./vi/student/messaging.json"),
    () => import("./vi/student/mock-interview.json"),
    () => import("./vi/student/profile.json"),
    () => import("./vi/university/advertising-creatives.json"),
    () => import("./vi/university/advertising-oversight.json"),
    () => import("./vi/university/ai-settings.json"),
    () => import("./vi/university/analytics.json"),
    () => import("./vi/university/billing-oversight.json"),
    () => import("./vi/university/career-outcomes.json"),
    () => import("./vi/university/dashboard.json"),
    () => import("./vi/university/career-services.json"),
    () => import("./vi/university/cv-templates-admin.json"),
    () => import("./vi/university/events-moderation.json"),
    () => import("./vi/university/global-pipeline.json"),
    () => import("./vi/university/jobs-moderation.json"),
    () => import("./vi/university/mock-interview-oversight.json"),
    () => import("./vi/university/moderation-hub.json"),
    () => import("./vi/university/notification-templates.json"),
    () => import("./vi/university/partners-detail.json"),
    () => import("./vi/university/partners-review.json"),
    () => import("./vi/university/platform-trust.json"),
    () => import("./vi/university/reports.json"),
    () => import("./vi/university/reviews-moderation.json"),
    () => import("./vi/university/users.json"),
  ],
  en: [
    () => import("./en/admin/console.json"),
    () => import("./en/auth/auth.json"),
    () => import("./en/partner/advertising.json"),
    () => import("./en/partner/billing.json"),
    () => import("./en/partner/candidates.json"),
    () => import("./en/partner/company-profile.json"),
    () => import("./en/partner/events-manage.json"),
    () => import("./en/partner/interviews.json"),
    () => import("./en/partner/offers.json"),
    () => import("./en/partner/partner-reviews.json"),
    () => import("./en/partner/pipeline.json"),
    () => import("./en/partner/reviews.json"),
    () => import("./en/partner/scorecards.json"),
    () => import("./en/partner/talent-pool.json"),
    () => import("./en/partner/team.json"),
    () => import("./en/public/events.json"),
    () => import("./en/public/landing.json"),
    () => import("./en/public/marketplace.json"),
    () => import("./en/settings/notifications.json"),
    () => import("./en/settings/settings.json"),
    () => import("./en/shared/common.json"),
    () => import("./en/shared/report.json"),
    () => import("./en/shared/shell.json"),
    () => import("./en/shared/workflow-builder.json"),
    () => import("./en/student/ai-assistant.json"),
    () => import("./en/student/applications.json"),
    () => import("./en/student/cv.json"),
    () => import("./en/student/dashboard.json"),
    () => import("./en/student/feedback.json"),
    () => import("./en/student/jobs.json"),
    () => import("./en/student/messaging.json"),
    () => import("./en/student/mock-interview.json"),
    () => import("./en/student/profile.json"),
    () => import("./en/university/advertising-creatives.json"),
    () => import("./en/university/advertising-oversight.json"),
    () => import("./en/university/ai-settings.json"),
    () => import("./en/university/analytics.json"),
    () => import("./en/university/billing-oversight.json"),
    () => import("./en/university/career-outcomes.json"),
    () => import("./en/university/dashboard.json"),
    () => import("./en/university/career-services.json"),
    () => import("./en/university/cv-templates-admin.json"),
    () => import("./en/university/events-moderation.json"),
    () => import("./en/university/global-pipeline.json"),
    () => import("./en/university/jobs-moderation.json"),
    () => import("./en/university/mock-interview-oversight.json"),
    () => import("./en/university/moderation-hub.json"),
    () => import("./en/university/notification-templates.json"),
    () => import("./en/university/partners-detail.json"),
    () => import("./en/university/partners-review.json"),
    () => import("./en/university/platform-trust.json"),
    () => import("./en/university/reports.json"),
    () => import("./en/university/reviews-moderation.json"),
    () => import("./en/university/users.json"),
  ],
};

export async function loadMessages(locale: AppLocale): Promise<MessageTree> {
  let messages: MessageTree = {};
  for (const load of loaders[locale]) {
    messages = mergeMessages(messages, (await load()).default);
  }
  return messages;
}
