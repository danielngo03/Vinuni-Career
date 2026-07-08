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
 * Deterministic monochrome fallback shades (v9 Monochrome). Each company name
 * hashes to a consistent chip shade from the gray ramp, so the same company
 * always looks identical and a board of avatars reads as a calm gray grid — no
 * color, no gradient. The chip shades are theme-invariant (like the sibling
 * white logo box), and the initials use fixed ink so contrast holds in both
 * light and dark themes.
 */
const CHIP_SHADES = [
  "bg-[var(--gray-200)]",
  "bg-[var(--gray-300)]",
  "bg-[var(--gray-400)]",
] as const;

function nameHash(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return h % CHIP_SHADES.length;
}

const SIZES = {
  sm: "size-9 text-xs rounded-lg",
  md: "size-12 text-sm rounded-xl",
  lg: "size-16 text-lg rounded-2xl",
} as const;

/**
 * Company logo with a deterministic monochrome initials fallback. When
 * `logo_url` is null (the common path until logos are seeded) each company gets
 * a stable gray-ramp chip with ink initials, keeping the board calm and on
 * brand. The label is decorative; the surrounding link/heading carries the
 * accessible name.
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
  const shade = CHIP_SHADES[nameHash(name)];
  return (
    <span
      aria-hidden
      className={cn(
        "flex shrink-0 items-center justify-center font-bold text-[var(--gray-900)]",
        shade,
        SIZES[size],
        className,
      )}
    >
      {initials(name)}
    </span>
  );
}
