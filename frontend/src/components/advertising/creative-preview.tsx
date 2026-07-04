"use client";

import { useEffect, useState } from "react";
import { ImageBroken, Image as ImageIcon } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import type { StatusTone } from "@/components/ui";
import {
  CREATIVE_SLOT_SPECS,
  ratioToCss,
  type CreativeModerationStatus,
  type CreativeSlot,
} from "@/lib/api";

/** Creative review state → StatusBadge tone (never color-only; always paired with a label). */
export function creativeStatusTone(
  status: CreativeModerationStatus | string,
): StatusTone {
  if (status === "approved") return "active";
  if (status === "rejected") return "rejected";
  return "pending";
}

/** object-position from a 0..1 focal point. */
export function focalPosition(focal: { x: number; y: number }): string {
  const x = Math.round(clamp01(focal.x) * 100);
  const y = Math.round(clamp01(focal.y) * 100);
  return `${x}% ${y}%`;
}

function clamp01(n: number): number {
  if (Number.isNaN(n)) return 0.5;
  return Math.min(1, Math.max(0, n));
}

/**
 * Cropped creative image with a focal-point `object-position`. Falls back to a
 * neutral, honest placeholder when the image cannot be served — the public serve
 * route only returns bytes for an APPROVED creative on an ACTIVE placement, so a
 * `pending`/paused creative resolves to 404 rather than leaking bytes. `localSrc`
 * (an object URL for a just-picked file) is used when present so a staged upload
 * previews immediately. No raw storage key is ever referenced.
 */
export function CreativeImage({
  src,
  localSrc,
  alt,
  focal,
  unavailableLabel,
  className,
}: {
  src: string | null;
  localSrc?: string | null;
  alt: string | null;
  focal: { x: number; y: number };
  unavailableLabel: string;
  className?: string;
}) {
  const effective = localSrc ?? src;
  const [broken, setBroken] = useState(false);

  // Reset the error state whenever the source changes.
  useEffect(() => {
    setBroken(false);
  }, [effective]);

  if (!effective || broken) {
    return (
      <div
        className={cn(
          "flex flex-col items-center justify-center gap-1.5 bg-[var(--bg-subtle)] text-[var(--text-muted)]",
          className,
        )}
      >
        {broken ? (
          <ImageBroken aria-hidden weight="duotone" className="size-7" />
        ) : (
          <ImageIcon aria-hidden weight="duotone" className="size-7" />
        )}
        <span className="px-3 text-center text-[11px] font-medium leading-tight">
          {unavailableLabel}
        </span>
      </div>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element -- dynamic external serve URL / blob; Next Image is not applicable.
    <img
      src={effective}
      alt={alt ?? ""}
      onError={() => setBroken(true)}
      className={cn("h-full w-full object-cover", className)}
      style={{ objectPosition: focalPosition(focal) }}
    />
  );
}

/**
 * Desktop + mobile placement preview frames for a slot, cropping the source with
 * the focal point so partners/moderators see exactly how the banner renders in
 * each viewport (spec §6 "preview exact desktop/mobile placements").
 */
export function SlotPreviewFrames({
  slot,
  src,
  localSrc,
  alt,
  focal,
  desktopLabel,
  mobileLabel,
  unavailableLabel,
}: {
  slot: CreativeSlot | string;
  src: string | null;
  localSrc?: string | null;
  alt: string | null;
  focal: { x: number; y: number };
  desktopLabel: string;
  mobileLabel: string;
  unavailableLabel: string;
}) {
  const spec = CREATIVE_SLOT_SPECS[slot as CreativeSlot];
  const desktopRatio = ratioToCss(spec?.desktop_ratio) ?? "16 / 9";
  const mobileRatio = ratioToCss(spec?.mobile_ratio) ?? "1 / 1";

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_auto]">
      <figure className="min-w-0">
        <figcaption className="mb-1 flex items-center justify-between text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
          <span>{desktopLabel}</span>
          {spec?.desktop && <span className="font-mono">{spec.desktop}</span>}
        </figcaption>
        <div
          className="w-full overflow-hidden rounded-lg border border-[var(--border-default)]"
          style={{ aspectRatio: desktopRatio }}
        >
          <CreativeImage
            src={src}
            localSrc={localSrc}
            alt={alt}
            focal={focal}
            unavailableLabel={unavailableLabel}
            className="h-full"
          />
        </div>
      </figure>
      <figure className="w-28 shrink-0 sm:w-24">
        <figcaption className="mb-1 flex items-center justify-between text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
          <span>{mobileLabel}</span>
          {spec?.mobile && <span className="font-mono">{spec.mobile}</span>}
        </figcaption>
        <div
          className="w-full overflow-hidden rounded-lg border border-[var(--border-default)]"
          style={{ aspectRatio: mobileRatio }}
        >
          <CreativeImage
            src={src}
            localSrc={localSrc}
            alt={alt}
            focal={focal}
            unavailableLabel={unavailableLabel}
            className="h-full"
          />
        </div>
      </figure>
    </div>
  );
}
