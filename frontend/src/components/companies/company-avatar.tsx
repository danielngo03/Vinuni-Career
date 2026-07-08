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

/**
 * Deterministic gradient palette for initials fallback. Each company name
 * hashes to a consistent index, so the same company always gets the same color.
 */
const GRADIENT_PALETTE = [
  "linear-gradient(135deg, #2563EB 0%, #1E40AF 100%)", // blue
  "linear-gradient(135deg, #0D9488 0%, #0F766E 100%)", // teal
  "linear-gradient(135deg, #7C3AED 0%, #5B21B6 100%)", // violet
  "linear-gradient(135deg, #DC2626 0%, #991B1B 100%)", // red
  "linear-gradient(135deg, #D97706 0%, #B45309 100%)", // amber
  "linear-gradient(135deg, #059669 0%, #065F46 100%)", // emerald
  "linear-gradient(135deg, #DB2777 0%, #9D174D 100%)", // pink
  "linear-gradient(135deg, #2563EB 0%, #0D9488 100%)", // blue-teal
] as const;

function nameHash(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return h % GRADIENT_PALETTE.length;
}

const SIZES = {
  sm: "size-9 text-xs rounded-lg",
  md: "size-12 text-sm rounded-xl",
  lg: "size-16 text-lg rounded-2xl",
} as const;

/**
 * Company logo with a deterministic gradient-initials fallback. When `logo_url`
 * is null (the common path until logos are seeded) each company gets a unique,
 * stable gradient from the palette, making the board visually varied. The label
 * is decorative; the surrounding link/heading carries the accessible name.
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
          "shrink-0 object-contain border border-[var(--border-subtle)] bg-white",
          SIZES[size],
          className,
        )}
      />
    );
  }
  const gradient = GRADIENT_PALETTE[nameHash(name)];
  return (
    <span
      aria-hidden
      className={cn(
        "flex shrink-0 items-center justify-center font-bold text-white",
        SIZES[size],
        className,
      )}
      style={{ background: gradient }}
    >
      {initials(name)}
    </span>
  );
}
