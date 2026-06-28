import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatNumber(value: number | string) {
  const parsed = typeof value === "string" ? Number(value) : value;
  return Number.isFinite(parsed)
    ? new Intl.NumberFormat("vi-VN").format(parsed)
    : String(value);
}

export function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(-2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}
