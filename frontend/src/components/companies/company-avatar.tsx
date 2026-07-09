import { cn } from "@/lib/utils";

/** Derive up to two uppercase initials from a company display name. */
function initials(name: string): string {
  const parts = name
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2);
  if (parts.length === 0) return "?";
  return parts.map((p) => p[0]!.toUpperCase()).join("");
}

const SIZES = {
  sm: "size-9 text-xs rounded-lg",
  md: "size-12 text-sm rounded-xl",
  lg: "size-16 text-lg rounded-2xl",
} as const;

/**
 * Company logo with a neutral initials fallback. When `logo_url` is null (the
 * common path until logos are seeded) the initials render as ink on a muted
 * surface — monochrome by design, so color always carries meaning elsewhere and
 * never decorates a logo placeholder. The label is decorative; the surrounding
 * link/heading carries the accessible name.
 */
export function CompanyAvatar({
  name,
  logoUrl,
  size = "md",
  className,
}: {
  name: string;
  logoUrl?: string | null;
  size?: keyof typeof SIZES;
  className?: string;
}) {
  if (logoUrl) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={logoUrl}
        alt=""
        aria-hidden
        className={cn(
          "shrink-0 object-contain border border-[var(--border-subtle)] bg-[var(--surface-card)]",
          SIZES[size],
          className,
        )}
      />
    );
  }
  return (
    <span
      aria-hidden
      className={cn(
        "flex shrink-0 items-center justify-center border border-[var(--border-subtle)] bg-[var(--bg-muted)] font-bold text-[var(--text-primary)]",
        SIZES[size],
        className,
      )}
    >
      {initials(name)}
    </span>
  );
}
