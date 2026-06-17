import type { ApiError, Job, MatchResult, ParsedStudentProfile, ReviewResult, Session, StudentJobMatch, StudentProfile, TeacherRagReport } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

type RequestOptions = Omit<RequestInit, "headers"> & {
  headers?: Record<string, string>;
};

async function request<T>(path: string, session: Session, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {
    "X-Demo-Role": session.role,
    "X-Demo-User-Id": session.userId,
    ...(options.headers || {}),
  };

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const error = (await response.json()) as ApiError;
      if (error.detail) {
        message = typeof error.detail === "string" ? error.detail : JSON.stringify(error.detail);
      }
    } catch {
      const text = await response.text();
      if (text) {
        message = text;
      }
    }
    throw new Error(message);
  }

  return (await response.json()) as T;
}

export const api = {
  root: () => fetch(`${API_BASE}/`).then((response) => response.json()),

  parseJob: (session: Session, payload: Record<string, unknown>) =>
    request<Job>("/jobs/parse", session, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  parseJobUpload: (session: Session, file: File) => {
    const form = new FormData();
    form.append("company_id", session.userId);
    form.append("file", file);
    return request<Job>("/jobs/parse-upload", session, {
      method: "POST",
      body: form,
    });
  },

  saveJob: (session: Session, job: Job) =>
    request<Job>("/jobs", session, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(job),
    }),

  listJobs: (session: Session) => request<Job[]>("/jobs", session),
  listOpenJobs: (session: Session) => request<Job[]>("/jobs/open", session),
  openJob: (session: Session, jobId: string) => request<Job>(`/jobs/${jobId}/open`, session, { method: "POST" }),
  closeJob: (session: Session, jobId: string) => request<Job>(`/jobs/${jobId}/close`, session, { method: "POST" }),
  deleteJob: (session: Session, jobId: string) => request<{ status: string; job_id: string }>(`/jobs/${jobId}`, session, { method: "DELETE" }),
  matchJob: (session: Session, jobId: string, strongMatch: number, partialMatch: number) =>
    request<MatchResult[]>(`/jobs/${jobId}/match`, session, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ strong_match: strongMatch, partial_match: partialMatch }),
    }),

  parseCvText: (session: Session, rawText: string) =>
    request<ParsedStudentProfile>("/students/cv/parse", session, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ raw_text: rawText }),
    }),

  parseCvUpload: (session: Session, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ParsedStudentProfile>("/students/cv/parse-upload", session, {
      method: "POST",
      body: form,
    });
  },

  saveStudent: (session: Session, student: StudentProfile) =>
    request<StudentProfile>("/students", session, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(student),
    }),

  listMyStudents: (session: Session) => request<StudentProfile[]>("/agents/student-profile/students", session),
  listStudentsForEnterprise: (session: Session) => request<StudentProfile[]>("/students", session),
  matchStudentJobs: (session: Session, studentId: string, strongMatch: number, partialMatch: number) =>
    request<StudentJobMatch[]>(`/students/${studentId}/match-jobs`, session, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ strong_match: strongMatch, partial_match: partialMatch }),
    }),

  reviewStudentJob: (session: Session, studentId: string, jobId: string, strongMatch: number, partialMatch: number, useLlm = true) =>
    request<ReviewResult>(`/students/${studentId}/jobs/${jobId}/review`, session, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        strong_match: strongMatch,
        partial_match: partialMatch,
        use_llm: useLlm,
      }),
    }),

  detectTeacherSource: (session: Session, sourceUrl: string) =>
    request<{ source_type: string }>("/agents/teacher-rag/detect", session, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_url: sourceUrl }),
    }),

  runTeacherRag: (session: Session, payload: Record<string, unknown>) =>
    request<TeacherRagReport>("/agents/teacher-rag/run", session, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
};
