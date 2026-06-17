import type { CompatMatch, Company, FlowMode, Job, Student, StudentJobMatch } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

type RequestOptions = Omit<RequestInit, "headers"> & {
  headers?: Record<string, string>;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: options.headers || {},
  });

  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (body.detail) message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      const text = await response.text();
      if (text) message = text;
    }
    throw new Error(message);
  }

  return (await response.json()) as T;
}

function thresholdsForMode(mode: FlowMode) {
  if (mode === "strict") return { strong_match: 0.88, partial_match: 0.7 };
  if (mode === "intern_friendly") return { strong_match: 0.74, partial_match: 0.52 };
  return { strong_match: 0.8, partial_match: 0.6 };
}

export const api = {
  listStudents: () => request<Student[]>("/students"),
  listCompanies: () => request<Company[]>("/companies").catch(() => [] as Company[]),
  listJobs: () => request<Job[]>("/jobs"),
  updateJobStatus: (jobId: string, status: "open" | "closed") =>
    request<Job>(`/jobs/${jobId}/${status === "open" ? "open" : "close"}`, { method: "POST" }),
  deleteJob: (jobId: string) => request<{ status: string; job_id: string }>(`/jobs/${jobId}`, { method: "DELETE" }),
  matchStudentJobs: (studentId: string, mode: FlowMode) =>
    request<StudentJobMatch[]>(`/students/${studentId}/match-jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(thresholdsForMode(mode)),
    }),
  matchJobCandidates: (jobId: string, mode: FlowMode) =>
    request<CompatMatch[]>(`/jobs/${jobId}/match`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(thresholdsForMode(mode)),
    }),
};
