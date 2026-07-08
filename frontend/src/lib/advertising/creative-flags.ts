/**
 * Pure helpers for the creative policy pre-flag display (spec §5/§9).
 *
 * A creative upload can return advisory `policy_flags` (dimension mismatch,
 * low-res, banned claim, off-platform contact, impersonation). These are
 * ADVISORY ONLY — the creative stays `pending` for a human reviewer and a flag
 * never auto-rejects. The UI shows a calm "needs review — flagged: …" note, so
 * wording here maps to localized, non-alarming labels (kept in the component's
 * i18n namespace). No provider/model/internal detail is ever surfaced.
 */

import type { CreativePolicyFlag } from "@/lib/api";

/** The five deterministic pre-check codes the backend can raise. */
export const CREATIVE_POLICY_CODES = [
  "creative_dimension_mismatch",
  "creative_low_resolution",
  "banned_claim",
  "off_platform_contact",
  "disclosure_impersonation",
] as const;

export type KnownCreativePolicyCode = (typeof CREATIVE_POLICY_CODES)[number];

const KNOWN: ReadonlySet<string> = new Set(CREATIVE_POLICY_CODES);

/** True when the upload came back with at least one advisory flag. */
export function hasPolicyFlags(
  flags: CreativePolicyFlag[] | null | undefined,
): boolean {
  return Array.isArray(flags) && flags.length > 0;
}

/**
 * Message-key suffix for a flag code. An unrecognized code (forward-compatible
 * with a new backend rule) maps to a generic `unknown` label rather than leaking
 * a raw code to the partner.
 */
export function policyFlagKey(code: string): string {
  return KNOWN.has(code) ? code : "unknown";
}

/**
 * Distinct, order-preserving flag keys for display (de-duped so a repeated code
 * is only shown once). Empty when there are no flags.
 */
export function policyFlagKeys(
  flags: CreativePolicyFlag[] | null | undefined,
): string[] {
  if (!Array.isArray(flags)) return [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const flag of flags) {
    if (typeof flag?.code !== "string") continue;
    const key = policyFlagKey(flag.code);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(key);
  }
  return out;
}

const SEVERITY_RANK: Record<string, number> = { high: 3, medium: 2, low: 1 };

/**
 * Collapse the flags into a single severity (high > medium > low), or `null`
 * when there are none. Used only to decide emphasis — a flag is advisory
 * regardless of severity.
 */
export function overallSeverity(
  flags: CreativePolicyFlag[] | null | undefined,
): "high" | "medium" | "low" | null {
  if (!Array.isArray(flags) || flags.length === 0) return null;
  let best = 0;
  for (const flag of flags) {
    const rank = SEVERITY_RANK[String(flag?.severity)] ?? 0;
    if (rank > best) best = rank;
  }
  if (best === 3) return "high";
  if (best === 2) return "medium";
  return "low";
}
