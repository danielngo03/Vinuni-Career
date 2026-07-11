import { Megaphone } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Shared inbox-row building blocks (v10). Both the full-page `MessagingScreen`
 * and the slide-in `MessagingCenter` render identical counterparty avatar tiles,
 * so the tile + initials + deterministic hue helpers live here to stay in sync.
 *
 * Colour is CONTENT, not shell: avatar tiles use soft data-viz tints keyed to
 * the (server-masked) counterparty label, so the inbox reads with density
 * without any loud fills. Announcement threads always use the amber
 * megaphone tile, matching the announcement marker elsewhere.
 */

/** Locked, colourblind-safe data-viz hues used for counterparty avatar tints. */
const AVATAR_HUES = ["indigo", "teal", "violet", "sky", "emerald"] as const;

/** Deterministic soft hue for a counterparty avatar tile (stable per label). */
export function avatarHue(seed: string): (typeof AVATAR_HUES)[number] {
  let h = 0;
  for (let i = 0; i < seed.length; i += 1) {
    h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return AVATAR_HUES[h % AVATAR_HUES.length]!;
}

/** Up-to-two-character initials from a (possibly masked) server label. */
export function initialsFrom(label: string): string {
  const words = label
    .trim()
    .split(/\s+/)
    .map((w) => w.replace(/[^\p{L}\p{N}]/gu, ""))
    .filter(Boolean);
  const out = words
    .slice(0, 2)
    .map((w) => w[0]!)
    .join("")
    .toUpperCase();
  return out || label.trim().charAt(0).toUpperCase() || "?";
}

/**
 * Counterparty avatar tile: an amber megaphone for announcements, otherwise a
 * soft-tinted initials tile. Identity is the server label only — this renders
 * initials of the masked-or-real label verbatim and never reconstructs a name.
 */
export function ThreadAvatar({
  label,
  announcement,
  size = "md",
  className,
}: {
  label: string;
  announcement: boolean;
  size?: "sm" | "md";
  className?: string;
}) {
  const dim = size === "sm" ? "size-9" : "size-10";

  if (announcement) {
    return (
      <span
        aria-hidden
        className={cn("flex shrink-0 items-center justify-center rounded-xl", dim, className)}
        style={{ background: "var(--content-warning-soft)", color: "var(--content-warning)" }}
      >
        <Megaphone strokeWidth={1.8} className="size-[18px]" />
      </span>
    );
  }

  const hue = avatarHue(label);
  return (
    <span
      aria-hidden
      className={cn(
        "flex shrink-0 items-center justify-center rounded-xl type-body font-semibold",
        dim,
        className,
      )}
      style={{ background: `var(--viz-${hue}-soft)`, color: `var(--viz-${hue})` }}
    >
      {initialsFrom(label)}
    </span>
  );
}
