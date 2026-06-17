export type SkillDetail = {
  score?: number;
  confidence?: number;
  evidence?: string[];
  required_level?: number;
  importance?: number;
  required?: boolean;
};

export type Student = {
  student_id: string;
  name?: string;
  skills: Record<string, SkillDetail>;
  metadata?: Record<string, unknown>;
};

export type Company = {
  company_id: string;
  name: string;
  industry?: string;
  metadata?: Record<string, unknown>;
};

export type Job = {
  job_id: string;
  company_id: string;
  title: string;
  status?: "open" | "closed" | "draft" | string;
  location?: string;
  employment_type?: string;
  salary_range?: string;
  benefits?: string[];
  skills: Record<string, SkillDetail>;
  metadata?: Record<string, unknown>;
};

export type StudentJobMatch = {
  job: Job;
  match: CompatMatch;
};

export type CompatMatch = {
  job_id: string;
  student_id: string;
  student_name?: string;
  match_score: number;
  match_status: "strong_match" | "partial_match" | "not_match";
  matched_skills: string[];
  missing_or_weak_skills: Record<string, SkillGap>;
  explanation: string;
};

export type SkillGap = {
  user_score: number;
  required_level: number;
  gap: number;
  importance: number;
  required: boolean;
};

export type FlowMode = "balanced" | "strict" | "intern_friendly";

export type View = "overview" | "student" | "company";
