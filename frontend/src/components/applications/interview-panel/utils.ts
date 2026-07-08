import type { InterviewMode } from "@/lib/api";

/* --------------------------- datetime helpers ---------------------------- */

/** ISO -> `YYYY-MM-DDTHH:mm` in the viewer's local time (for `datetime-local`). */
export function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}`;
}

/** `datetime-local` value -> ISO 8601 (UTC). Empty -> null. */
export function localToIso(value: string): string | null {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString();
}

export type InterviewFormState = {
  mode: InterviewMode;
  scheduledAt: string;
  durationMinutes: number;
  location: string;
  meetingLink: string;
  title: string;
  notes: string;
  assigneeIds: string[];
};

export const EMPTY_INTERVIEW_FORM: InterviewFormState = {
  mode: "onsite",
  scheduledAt: "",
  durationMinutes: 60,
  location: "",
  meetingLink: "",
  title: "",
  notes: "",
  assigneeIds: [],
};
