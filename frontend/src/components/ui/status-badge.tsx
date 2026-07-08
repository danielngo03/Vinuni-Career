import { SealCheck, Handshake, Star } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import type { InventoryDisclosure } from "@/lib/api";

/**
 * Recruitment + tier + disclosure badges (DESIGN.md §5.3).
 * Color is never the only signal — every badge carries a text label.
 */
export type StatusTone =
  | "pending"
  | "active"
  | "rejected"
  | "draft"
  | "closed"
  | "offer"
  | "accepted"
  | "verified"
  | "featured"
  | "info";

const TONES: Record<StatusTone, string> = {
  pending:
    "bg-[var(--amber-100)] text-[var(--amber-700)] border-[var(--amber-600)]/40",
  active:
    "bg-[var(--teal-50)] text-[var(--teal-600)] border-[var(--teal-500)]/40",
  accepted:
    "bg-[var(--teal-50)] text-[var(--teal-600)] border-[var(--teal-500)]/40",
  rejected:
    "bg-[var(--red-50)] text-[var(--brand-red)] border-[var(--red-400)]/40",
  draft:
    "bg-[var(--gray-100)] text-[var(--gray-500)] border-[var(--gray-300)]",
  closed:
    "bg-[var(--gray-200)] text-[var(--gray-600)] border-[var(--gray-300)]",
  offer:
    "bg-[#eef2fb] text-[var(--navy-600)] border-[#b0bce0]",
  verified: "bg-[var(--brand-teal)] text-white border-transparent",
  featured: "bg-[var(--brand-red)] text-white border-transparent",
  info: "bg-[var(--blue-50)] text-[var(--brand-primary)] border-[var(--blue-200)]",
};

export interface StatusBadgeProps {
  tone: StatusTone;
  children: React.ReactNode;
  className?: string;
}

export function StatusBadge({ tone, children, className }: StatusBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold tracking-wide",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/**
 * Sponsored / ad disclosure label. NON-REMOVABLE per DESIGN.md §9 and
 * SECURITY_PRIVACY ads compliance. The text and styling are fixed by the
 * design system; callers cannot hide it. Pass `variant="ad"` for "Quảng cáo".
 */
export function SponsoredLabel({
  label,
  className,
}: {
  /** Localized disclosure text, e.g. "Được tài trợ" or "Quảng cáo". */
  label: string;
  className?: string;
}) {
  return (
    <span
      data-disclosure="sponsored"
      className={cn("sponsored-label", className)}
    >
      {label}
    </span>
  );
}

/**
 * Polished, class-keyed disclosure label for marketplace campaign inventory
 * (PRODUCT_INTERACTION_VISUAL_REALISM_SPEC §4/§7). The `label` text is the
 * SERVER-localized polished copy ("Đối tác tài trợ", "VinUni tuyển chọn", …) —
 * never blunt ad-tech wording.
 *
 * Only `paid_sponsored` is PAID: it renders the non-removable amber sponsored
 * chip (identical to {@link SponsoredLabel}). The editorial/partnership classes
 * (`university_curated`, `strategic_partner`, `featured`) render with their own
 * truthful, distinct tones and are NEVER styled as paid. Each chip carries a
 * text label, so meaning is never color-only (WCAG).
 *
 * Shared with the advertising-admin surfaces — keep the class→style mapping in
 * sync there.
 */
const DISCLOSURE_CHIP: Record<
  string,
  { cls: string; icon: React.ElementType | null }
> = {
  university_curated: {
    cls: "border-[var(--teal-500)]/45 bg-[var(--teal-50)] text-[var(--teal-600)]",
    icon: SealCheck,
  },
  strategic_partner: {
    cls: "border-[var(--navy-600)]/30 bg-[#eef2fb] text-[var(--navy-600)]",
    icon: Handshake,
  },
  featured: {
    cls: "border-[var(--brand-red)]/30 bg-[var(--red-50)] text-[var(--brand-red)]",
    icon: Star,
  },
};

export function DisclosureLabel({
  disclosure,
  className,
}: {
  disclosure: InventoryDisclosure;
  className?: string;
}) {
  const isPaid =
    disclosure.is_paid || disclosure.class === "paid_sponsored";

  // Paid → non-removable amber chip (SponsoredLabel parity).
  if (isPaid) {
    return (
      <span
        data-disclosure="paid_sponsored"
        className={cn("sponsored-label", className)}
      >
        {disclosure.label}
      </span>
    );
  }

  const style =
    DISCLOSURE_CHIP[disclosure.class] ?? {
      cls: "border-[var(--border-default)] bg-[var(--bg-subtle)] text-[var(--text-secondary)]",
      icon: null,
    };
  const Icon = style.icon;

  return (
    <span
      data-disclosure={disclosure.class}
      className={cn(
        "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[0.65rem] font-bold uppercase tracking-wide",
        style.cls,
        className,
      )}
    >
      {Icon && <Icon aria-hidden weight="fill" className="size-3 shrink-0" />}
      {disclosure.label}
    </span>
  );
}
