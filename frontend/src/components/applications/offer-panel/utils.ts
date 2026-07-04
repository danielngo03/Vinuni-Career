import { OFFER_LIVE_STATUSES } from "@/lib/api";

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

/** ISO date -> `YYYY-MM-DD` for a `date` input. */
export function toDateInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function isLive(status: string): boolean {
  return (OFFER_LIVE_STATUSES as readonly string[]).includes(status);
}

export type OfferFormState = {
  positionTitle: string;
  department: string;
  startDate: string;
  salaryAmount: string;
  salaryCurrency: string;
  salaryPeriod: string;
  benefits: string;
  terms: string;
  expiry: string;
};

export const EMPTY_OFFER_FORM: OfferFormState = {
  positionTitle: "",
  department: "",
  startDate: "",
  salaryAmount: "",
  salaryCurrency: "VND",
  salaryPeriod: "monthly",
  benefits: "",
  terms: "",
  expiry: "",
};
