import Image from "next/image";
import { cn } from "@/lib/utils";

/**
 * VinUni Career lockup (v9 "Monochrome"): the V mark + a hairline divider +
 * the "VINUNI CAREER" wordmark. The mark ships in two cuts — `logo-dark.png`
 * (black, for light surfaces) and `logo-light.png` (white, for dark surfaces) —
 * swapped purely in CSS via `[data-theme]` (.theme-logo-light/.theme-logo-dark)
 * so no client JS is needed.
 *
 * - `inverted` — forces the white cut + white text for permanently dark
 *   surfaces (hero/footer) regardless of the active theme.
 * - `showTagline=false` — compact form: the mark only (tight ops topbars).
 */
export function BrandMark({
  inverted = false,
  showTagline = true,
  className,
  wordmarkClassName,
}: {
  inverted?: boolean;
  showTagline?: boolean;
  className?: string;
  wordmarkClassName?: string;
}) {
  const mark = inverted ? (
    <Image
      src="/brand/logo-light.png"
      alt="VinUni Career"
      width={30}
      height={30}
      priority
      className="shrink-0 object-contain"
    />
  ) : (
    <>
      <Image
        src="/brand/logo-dark.png"
        alt="VinUni Career"
        width={30}
        height={30}
        priority
        className="theme-logo-light shrink-0 object-contain"
      />
      <Image
        src="/brand/logo-light.png"
        alt=""
        aria-hidden
        width={30}
        height={30}
        className="theme-logo-dark shrink-0 object-contain"
      />
    </>
  );

  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      {mark}
      {showTagline && (
        <>
          <span
            aria-hidden
            className={cn(
              "h-5 w-px shrink-0",
              inverted ? "bg-white/30" : "bg-[var(--border-strong)]",
            )}
          />
          <span
            className={cn(
              "whitespace-nowrap text-[0.6875rem] font-extrabold uppercase tracking-[0.12em]",
              inverted ? "text-white" : "text-[var(--text-primary)]",
              wordmarkClassName,
            )}
          >
            VinUni Career
          </span>
        </>
      )}
    </span>
  );
}
