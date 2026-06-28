import type { components } from "./schema";

export type Portal = "student" | "partner" | "university";
type Schema = components["schemas"];

export type User = Schema["UserView"];
export type Identity = Omit<Schema["IdentityView"], "portal"> & {
  portal: Portal;
};
export type TokenResponse = Omit<
  Schema["TokenResponse"],
  "user" | "identities"
> & {
  user: User;
  identities: Identity[];
  access_scope: string;
  pending_registration_id?: string | null;
};

export interface AuthSession {
  user: User;
  identities: Identity[];
  active_identity: Identity | null;
}

export type MetricItem = Schema["MetricItem"];
export type DashboardIdentity = Omit<Schema["DashboardIdentity"], "portal"> & {
  portal: Portal;
};
export type DashboardJob = Schema["DashboardJob"];
export type DashboardApplication = Schema["DashboardApplication"];
export type DashboardCV = Schema["DashboardCV"];
export type DashboardEvent = Schema["DashboardEvent"];
export type TrendPoint = Schema["DashboardTrendPoint"];
export type Activity = Schema["DashboardActivity"];
export type PartnerCandidate = Schema["PartnerCandidate"];
export type Job = Schema["JobView"];
export type JobPage = Schema["JobPage"];
export type JobApplication = Schema["JobApplicationView"];
export type CV = Schema["CVView"];
export type Event = Schema["EventView"];
export type Interview = Schema["InterviewView"];
export type Notification = Schema["NotificationView"];
export type CompanyReview = Schema["CompanyReviewView"];
export type DocumentRecord = Schema["DocumentResponse"];
export type DocumentUploadSession = Schema["UploadSessionResponse"];
export type AIRun = Schema["RunResponse"];
export type AIRunType = Schema["AIRunType"];
export type AgentCapability = Schema["AgentCapabilityResponse"];
export type SearchResponse = Schema["SearchResponse"];
export type SearchResult = Schema["SearchResult"];
export type Workflow = Schema["WorkflowView"];
export type WorkflowExecution = Schema["WorkflowExecutionView"];
export type AIUsageLog = Schema["AIUsageLogView"];

export type StudentDashboard = Omit<Schema["StudentDashboard"], "identity"> & {
  identity: DashboardIdentity;
};
export type PartnerDashboard = Omit<
  Schema["PartnerDashboard"],
  "identity" | "ai_usage"
> & {
  identity: DashboardIdentity;
  ai_usage: Record<string, number>;
};
export type UniversityDashboard = Omit<
  Schema["UniversityDashboard"],
  "identity" | "ai_usage" | "partners"
> & {
  identity: DashboardIdentity;
  ai_usage: Record<string, number>;
  partners: Array<{
    id: string;
    name: string;
    is_verified_partner: boolean;
    metadata: Record<string, unknown>;
  }>;
};

export type RegistrationStatus =
  | "DRAFT"
  | "SUBMITTED"
  | "VERIFYING"
  | "PENDING"
  | "UNDER_REVIEW"
  | "CHANGES_REQUESTED"
  | "NEEDS_CHANGES"
  | "RESUBMITTED"
  | "APPROVED"
  | "REJECTED"
  | "WITHDRAWN";

export interface RegistrationChecklistItem {
  code: string;
  label: string;
  field?: string | null;
  document?: string | null;
  resolved: boolean;
}

export interface RegistrationEvidence {
  id: string;
  version: number;
  provider: string;
  field_name: string;
  authority: string;
  trust_weight: number;
  confidence: number;
  extracted_value: Record<string, unknown>;
  provenance: Record<string, unknown>;
  mismatch: boolean;
  expires_at?: string | null;
}

export interface PendingRegistration {
  id: string;
  registration_type: "STUDENT" | "PARTNER";
  status: RegistrationStatus;
  university_org_id: string;
  submitted_at: string;
  reviewed_at?: string | null;
  review_note?: string | null;
  version: number;
  checklist: RegistrationChecklistItem[];
  assessment: {
    outcome?: "APPROVE" | "MANUAL_REVIEW" | "REQUEST_CHANGES";
    confidence?: number;
    low_risk?: boolean;
    reasons?: string[];
    missing_items?: RegistrationChecklistItem[];
  };
  policy_snapshot: {
    mode?: "DISABLED" | "SHADOW" | "AUTO_LOW_RISK";
    model_version?: string;
    confidence_threshold?: number;
  };
  applicant_name: string;
  applicant_email: string;
  summary: Record<string, unknown>;
  evidence: RegistrationEvidence[];
  allowed_actions: string[];
}

export type RegistrationQueueItem = PendingRegistration;

export interface VerificationPolicy {
  id: string;
  university_org_id: string;
  registration_type: "STUDENT" | "PARTNER";
  mode: "DISABLED" | "SHADOW" | "AUTO_LOW_RISK";
  global_kill_switch: boolean;
  confidence_threshold: number;
  required_providers: string[];
  required_documents: string[];
  sample_rate: number;
  model_version: string;
}
