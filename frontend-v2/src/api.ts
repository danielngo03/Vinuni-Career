import type { Job, Match, MatchingWeights, Student } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

type CompatMatch = {
  job_id?: string;
  student_id?: string;
  student_name?: string;
  match_score: number;
  match_status: string;
  matched_skills?: string[];
  missing_or_weak_skills?: Record<string, unknown>;
  explanation?: string;
};

type CompatStudentJobMatch = {
  job: {
    job_id: string;
    title: string;
    company_id?: string;
  };
  match: CompatMatch;
};

type CompatJob = {
  job_id: string;
  company_id: string;
  title: string;
  status: "draft" | "open" | "closed" | string;
  employment_type?: string | null;
  location?: string | null;
  salary_range?: string | null;
  benefits?: string[];
  skills?: Record<string, { required_level: number; importance: number; required: boolean }>;
  experience_requirements?: Job["experienceRequirements"];
  education_requirements?: Job["educationRequirements"];
  raw_text?: string;
  metadata?: Record<string, unknown>;
};

type CompatStudent = {
  student_id: string;
  name: string;
  target_position: string;
  skills: Record<string, { score: number; confidence: number; evidence: string[] }>;
  work_experience: Array<{
    title: string;
    company: string;
    duration: string;
    summary: string;
    score: number;
    score_reason: string;
  }>;
  education: Array<{
    degree: string;
    institution: string;
    year: string;
    summary: string;
    score: number;
    score_reason: string;
  }>;
  metadata: Record<string, unknown>;
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const extraHeaders = init.headers && !(init.headers instanceof Headers) && !Array.isArray(init.headers)
    ? init.headers
    : {};
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Demo-User-Id": "frontend-v2",
      ...extraHeaders,
    },
  });

  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      const text = await response.text();
      if (text) message = text;
    }
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

function normalizeScore(score: number): number {
  return Math.round(score <= 1 ? score * 100 : score);
}

function decisionFromStatus(status: string): Match["decision"] {
  if (status === "strong_match" || status === "shortlist") return "Shortlist";
  if (status === "partial_match" || status === "review") return "Review";
  return "Gap";
}

function gapLabels(match: CompatMatch): string[] {
  const gaps = Object.keys(match.missing_or_weak_skills || {});
  return gaps.length ? gaps : ["Không có gap nổi bật"];
}

function toUiJob(job: CompatJob): Job {
  const skills = Object.entries(job.skills || {});
  return {
    id: job.job_id,
    companyId: job.company_id,
    companyName: job.company_id === "company_demo" ? "Công ty demo" : job.company_id,
    title: job.title,
    status: job.status === "open" ? "open" : job.status === "closed" ? "closed" : "closed",
    location: job.location || "Linh hoạt",
    employmentType: job.employment_type || "Thực tập",
    requiredSkills: skills.filter(([, detail]) => detail.required).map(([name]) => name),
    optionalSkills: skills.filter(([, detail]) => !detail.required).map(([name]) => name),
    salary: job.salary_range || "Thỏa thuận",
    experienceRequirements: job.experience_requirements,
    educationRequirements: job.education_requirements,
  };
}

function toCompatJob(job: Job): CompatJob {
  return {
    job_id: job.id,
    company_id: job.companyId,
    title: job.title,
    status: job.status,
    employment_type: job.employmentType,
    location: job.location,
    salary_range: job.salary,
    benefits: [],
    skills: Object.fromEntries([
      ...job.requiredSkills.map((skill) => [skill, { required_level: 7, importance: 1, required: true }] as const),
      ...job.optionalSkills.map((skill) => [skill, { required_level: 6, importance: 0.6, required: false }] as const),
    ]),
    experience_requirements: job.experienceRequirements,
    education_requirements: job.educationRequirements,
    raw_text: `${job.title}\nKỹ năng bắt buộc: ${job.requiredSkills.join(", ")}\nKỹ năng ưu tiên: ${job.optionalSkills.join(", ")}`,
    metadata: { source: "frontend-v2" },
  };
}

function toCompatStudent(student: Student): CompatStudent {
  return {
    student_id: student.id,
    name: student.name,
    target_position: student.target,
    skills: Object.fromEntries(
      student.skills.map((skill) => [
        skill.name,
        {
          score: skill.score,
          confidence: skill.confidence,
          evidence: [skill.evidence],
        },
      ]),
    ),
    work_experience: student.experiences.map((item) => ({
      title: item.title,
      company: item.company,
      duration: item.duration,
      summary: item.summary,
      score: item.score,
      score_reason: "Nhập từ hồ sơ demo frontend-v2.",
    })),
    education: student.education.map((item) => ({
      degree: item.degree,
      institution: item.institution,
      year: item.year,
      summary: `${student.major} | ${student.university}`,
      score: item.score,
      score_reason: "Nhập từ hồ sơ demo frontend-v2.",
    })),
    metadata: {
      source: "frontend-v2",
      university: student.university,
      major: student.major,
      graduation_year: student.graduationYear,
    },
  };
}

export const api = {
  parseJob: async (rawText: string, companyId = "company_demo"): Promise<Job> => {
    const parsed = await request<CompatJob>("/jobs/parse", {
      method: "POST",
      body: JSON.stringify({ raw_text: rawText, company_id: companyId }),
    });
    return toUiJob(parsed);
  },

  saveJob: async (job: Job): Promise<Job> => {
    const saved = await request<CompatJob>("/jobs", {
      method: "POST",
      body: JSON.stringify(toCompatJob(job)),
    });
    return toUiJob(saved);
  },

  matchStudentJobs: async (student: Student): Promise<Match[]> => {
    await request<CompatStudent>("/students", {
      method: "POST",
      body: JSON.stringify(toCompatStudent(student)),
    });

    const rows = await request<CompatStudentJobMatch[]>(`/students/${student.id}/match-jobs`, {
      method: "POST",
      body: JSON.stringify({ strong_match: 0.8, partial_match: 0.6 }),
    });

    return rows.map((row) => ({
      id: row.job.job_id,
      title: row.job.title,
      subtitle: row.job.company_id || "Công ty",
      score: normalizeScore(row.match.match_score),
      decision: decisionFromStatus(row.match.match_status),
      strengths: row.match.matched_skills?.length ? row.match.matched_skills : ["Chưa có kỹ năng khớp rõ"],
      gaps: gapLabels(row.match),
    }));
  },

  matchCandidates: async (job: Job, weights?: MatchingWeights): Promise<Match[]> => {
    await request<CompatJob>("/jobs", {
      method: "POST",
      body: JSON.stringify(toCompatJob(job)),
    });

    const rows = await request<CompatMatch[]>(`/jobs/${job.id}/match`, {
      method: "POST",
      body: JSON.stringify({
        strong_match: 0.8,
        partial_match: 0.6,
        config: weights,
      }),
    });

    return rows.map((row) => ({
      id: row.student_id || row.job_id || crypto.randomUUID(),
      title: row.student_name || row.student_id || "Ứng viên",
      subtitle: row.student_id || "Student",
      score: normalizeScore(row.match_score),
      decision: decisionFromStatus(row.match_status),
      strengths: row.matched_skills?.length ? row.matched_skills : ["Chưa có kỹ năng khớp rõ"],
      gaps: gapLabels(row),
    }));
  },
};
