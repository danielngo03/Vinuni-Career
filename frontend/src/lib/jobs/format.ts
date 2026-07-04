import type { JobSalary, JobLocationItem } from "@/lib/api";

/** Common Vietnamese province code → display name lookup for human-readable location labels. */
export const PROVINCE_LABELS: Record<string, string> = {
  "01": "Hà Nội",
  "02": "Hà Giang",
  "04": "Cao Bằng",
  "06": "Bắc Kạn",
  "08": "Tuyên Quang",
  "10": "Lào Cai",
  "11": "Điện Biên",
  "12": "Lai Châu",
  "14": "Sơn La",
  "15": "Yên Bái",
  "17": "Hoà Bình",
  "19": "Thái Nguyên",
  "20": "Lạng Sơn",
  "22": "Quảng Ninh",
  "24": "Bắc Giang",
  "25": "Phú Thọ",
  "26": "Vĩnh Phúc",
  "27": "Bắc Ninh",
  "30": "Hải Dương",
  "31": "Hải Phòng",
  "33": "Hưng Yên",
  "34": "Thái Bình",
  "35": "Hà Nam",
  "36": "Nam Định",
  "37": "Ninh Bình",
  "38": "Thanh Hóa",
  "40": "Nghệ An",
  "42": "Hà Tĩnh",
  "44": "Quảng Bình",
  "45": "Quảng Trị",
  "46": "Thừa Thiên Huế",
  "48": "Đà Nẵng",
  "49": "Quảng Nam",
  "51": "Quảng Ngãi",
  "52": "Bình Định",
  "54": "Phú Yên",
  "56": "Khánh Hòa",
  "58": "Ninh Thuận",
  "60": "Bình Thuận",
  "62": "Kon Tum",
  "64": "Gia Lai",
  "66": "Đắk Lắk",
  "67": "Đắk Nông",
  "68": "Lâm Đồng",
  "70": "Bình Phước",
  "72": "Tây Ninh",
  "74": "Bình Dương",
  "75": "Đồng Nai",
  "77": "Bà Rịa–Vũng Tàu",
  "79": "TP. Hồ Chí Minh",
  "80": "Long An",
  "82": "Tiền Giang",
  "83": "Bến Tre",
  "84": "Trà Vinh",
  "86": "Vĩnh Long",
  "87": "Đồng Tháp",
  "89": "An Giang",
  "91": "Kiên Giang",
  "92": "Cần Thơ",
  "93": "Hậu Giang",
  "94": "Sóc Trăng",
  "95": "Bạc Liêu",
  "96": "Cà Mau",
};

/**
 * Format a disclosed salary range. Returns null when salary is undisclosed
 * (the API returns `salary: null`) so callers can render a neutral fallback.
 */
export function formatSalary(
  salary: JobSalary | null | undefined,
  locale: string,
): string | null {
  if (!salary) return null;
  const { min, max, currency } = salary;
  if (min == null && max == null) return null;
  const cur = currency || "VND";
  const isVi = locale === "vi";
  const numberLocale = isVi ? "vi-VN" : "en-US";

  if (cur.toUpperCase() === "VND") {
    const compact = (value: number) => {
      const millions = value / 1_000_000;
      return new Intl.NumberFormat(numberLocale, {
        maximumFractionDigits: Number.isInteger(millions) ? 0 : 1,
      }).format(millions);
    };
    const unit = isVi ? "triệu" : "M VND";
    if (min != null && max != null) {
      if (min === max) return `${compact(min)} ${unit}`;
      return `${compact(min)} - ${compact(max)} ${unit}`;
    }
    if (min != null) return isVi ? `Từ ${compact(min)} ${unit}` : `From ${compact(min)} ${unit}`;
    return isVi ? `Tới ${compact(max as number)} ${unit}` : `Up to ${compact(max as number)} ${unit}`;
  }

  const nf = new Intl.NumberFormat(numberLocale);
  if (min != null && max != null) {
    if (min === max) return `${nf.format(min)} ${cur}`;
    return `${nf.format(min)} - ${nf.format(max)} ${cur}`;
  }
  if (min != null) return isVi ? `Từ ${nf.format(min)} ${cur}` : `From ${nf.format(min)} ${cur}`;
  return isVi ? `Tới ${nf.format(max as number)} ${cur}` : `Up to ${nf.format(max as number)} ${cur}`;
}

/** "Hanoi, Vietnam" / "Vietnam" — joins non-empty parts. */
export function formatLocation(
  city: string | null | undefined,
  country: string | null | undefined,
): string {
  return [city, country].filter(Boolean).join(", ") || "—";
}

/**
 * Format a `JobLocationItem` for display. Prefers city name, then province
 * code resolved to a human-readable label, then country. Never shows raw codes.
 */
export function formatJobLocationItem(item: JobLocationItem): string {
  if (item.city) return item.city;
  if (item.province_code && PROVINCE_LABELS[item.province_code]) {
    return PROVINCE_LABELS[item.province_code]!;
  }
  return item.country || "—";
}

/**
 * Server-authoritative salary label passthrough. Prefers the backend's
 * localized `salary_display.label` (e.g. "Thỏa thuận", "30 - 60 triệu", "Tới
 * 50 triệu") over any client-side re-derivation, falling back to
 * `formatSalary()` only when `salary_display` is absent (legacy rows).
 */
export function jobSalaryLabel(
  job: {
    salary?: JobSalary | null;
    salary_display?: { label: string } | null;
  },
  locale: string,
): string | null {
  return job.salary_display?.label ?? formatSalary(job.salary ?? null, locale);
}

/** Split a comma/newline separated string into trimmed, de-duped tags. */
export function parseTags(value: string | null | undefined): string[] {
  if (!value) return [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of value.split(/[,\n]/)) {
    const t = raw.trim();
    if (t && !seen.has(t.toLowerCase())) {
      seen.add(t.toLowerCase());
      out.push(t);
    }
  }
  return out;
}
