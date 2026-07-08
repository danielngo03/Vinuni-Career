/**
 * Creative policy pre-flag helpers — pure unit tests.
 *
 * Focus: detecting flags, mapping codes to safe message keys (unknown codes
 * never leak), de-duped display order, and the collapsed severity.
 */
import { describe, it, expect } from "vitest";
import type { CreativePolicyFlag } from "@/lib/api";
import {
  CREATIVE_POLICY_CODES,
  hasPolicyFlags,
  overallSeverity,
  policyFlagKey,
  policyFlagKeys,
} from "./creative-flags";

const flag = (
  code: string,
  severity = "medium",
): CreativePolicyFlag => ({ code, severity, detail: "d" });

describe("hasPolicyFlags", () => {
  it("is true only for a non-empty array", () => {
    expect(hasPolicyFlags([flag("banned_claim")])).toBe(true);
    expect(hasPolicyFlags([])).toBe(false);
    expect(hasPolicyFlags(null)).toBe(false);
    expect(hasPolicyFlags(undefined)).toBe(false);
  });
});

describe("policyFlagKey", () => {
  it("passes through every known backend code", () => {
    for (const code of CREATIVE_POLICY_CODES) {
      expect(policyFlagKey(code)).toBe(code);
    }
  });

  it("maps an unrecognized code to the generic unknown key (no raw leak)", () => {
    expect(policyFlagKey("some_new_backend_rule")).toBe("unknown");
    expect(policyFlagKey("")).toBe("unknown");
  });
});

describe("policyFlagKeys", () => {
  it("returns distinct, order-preserving keys", () => {
    const keys = policyFlagKeys([
      flag("banned_claim"),
      flag("off_platform_contact"),
      flag("banned_claim"),
    ]);
    expect(keys).toEqual(["banned_claim", "off_platform_contact"]);
  });

  it("collapses unknown codes to a single unknown entry", () => {
    const keys = policyFlagKeys([flag("x"), flag("y")]);
    expect(keys).toEqual(["unknown"]);
  });

  it("returns empty for no flags", () => {
    expect(policyFlagKeys(null)).toEqual([]);
    expect(policyFlagKeys([])).toEqual([]);
  });
});

describe("overallSeverity", () => {
  it("picks the highest severity present", () => {
    expect(
      overallSeverity([flag("creative_low_resolution", "low"), flag("banned_claim", "high")]),
    ).toBe("high");
    expect(
      overallSeverity([
        flag("creative_dimension_mismatch", "medium"),
        flag("creative_low_resolution", "low"),
      ]),
    ).toBe("medium");
    expect(overallSeverity([flag("creative_low_resolution", "low")])).toBe("low");
  });

  it("returns null for no flags", () => {
    expect(overallSeverity([])).toBeNull();
    expect(overallSeverity(null)).toBeNull();
  });
});
