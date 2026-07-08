import { JobModerationScreen } from "@/components/jobs/job-moderation-screen";

/**
 * Moderation hub. Jobs are the only moderated surface in Phase 1c, so the index
 * route renders the job moderation queue directly (it also lives at
 * `/university/moderation/jobs`). The sidebar `moderation` entry points here.
 */
export default function UniversityModerationPage() {
  return <JobModerationScreen />;
}
