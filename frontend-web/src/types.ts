export type Role = "enterprise" | "student" | "teacher";

export type Session = {
  role: Role;
  userId: string;
};

export type SkillRequirement = {
  required_level: number;
  importance: number;
  required: boolean;
};

export type StudentSkill = {
  score: number;
  confidence: number;
  evidence: string[];
};

export type Job = {
  job_id: string;
  company_id: string;
  title: string;
  status: "draft" | "open" | "closed";
  employment_type: string;
  location: string;
  salary_range: string;
  benefits: string[];
  skills: Record<string, SkillRequirement>;
  raw_text?: string;
  metadata?: Record<string, unknown>;
};

export type StudentProfile = {
  student_id: string;
  name: string;
  skills: Record<string, StudentSkill>;
  metadata?: Record<string, unknown>;
};

export type MatchResult = {
  job_id: string;
  student_id: string;
  student_name: string;
  match_score: number;
  match_status: "strong_match" | "partial_match" | "not_match";
  matched_skills: string[];
  missing_or_weak_skills: Record<
    string,
    {
      user_score: number;
      required_level: number;
      gap: number;
      importance: number;
      required: boolean;
    }
  >;
  explanation: string;
};

export type StudentJobMatch = {
  job: Job;
  match: MatchResult;
};

export type ReviewResult = {
  student_id: string;
  job_id: string;
  job_title: string;
  company_id: string;
  match: MatchResult;
  overall_assessment: string;
  match_level: string;
  strengths: string[];
  missing_skills: Array<Record<string, unknown>>;
  missing_keywords: string[];
  improvement_suggestions: string[];
  cv_improvements: string[];
  priority_actions: string[];
  _reviewer?: {
    reviewer_mode: string;
    model: string;
    api_key_configured: boolean;
    used_llm: boolean;
    fallback_used: boolean;
    error?: string | null;
  };
};

export type TeacherRagReport = {
  run_id: string;
  source_type: string;
  course_title: string;
  videos_found: number;
  videos_saved: number;
  videos_failed: number;
  chunks_created: number;
  chunks_output: string;
  report_output: string;
  videos: Array<Record<string, unknown>>;
};

export type ApiError = {
  detail?: string;
};
