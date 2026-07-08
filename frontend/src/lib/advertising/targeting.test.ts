/**
 * Targeting descriptor builder — pure unit tests.
 *
 * Focus: ONLY the six allowlisted dimensions survive, `automatic` clears all
 * dimensions, closed vocabularies are clamped, and a `university_restricted`
 * placement is detected as read-only.
 */
import { describe, it, expect } from "vitest";
import {
  buildTargetingDescriptor,
  descriptorFromPlacement,
  isUniversityRestricted,
  activeDimensions,
  countTargetingValues,
  normalizeDimensionValues,
  TARGETING_DIMENSIONS,
} from "./targeting";
import type { TargetingDescriptor } from "@/lib/api";

describe("buildTargetingDescriptor — allowlist safety", () => {
  it("keeps only the six allowlisted dimensions in manual mode", () => {
    const result = buildTargetingDescriptor("manual", {
      region: ["hanoi"],
      industry: ["fintech"],
      role_family: ["software_engineering"],
      work_mode: ["remote"],
      student_segment: ["student"],
      language: ["vi"],
      // Forbidden / non-allowlisted keys must be dropped entirely.
      email: ["a@b.com"],
      gender: ["female"],
      salary: ["high"],
      ad_id: ["xyz"],
    });
    expect(Object.keys(result.dimensions).sort()).toEqual(
      [...TARGETING_DIMENSIONS].sort(),
    );
    expect((result.dimensions as Record<string, unknown>).email).toBeUndefined();
    expect((result.dimensions as Record<string, unknown>).gender).toBeUndefined();
    expect((result.dimensions as Record<string, unknown>).salary).toBeUndefined();
    expect((result.dimensions as Record<string, unknown>).ad_id).toBeUndefined();
  });

  it("emits empty dimensions for automatic mode even if values are passed", () => {
    const result = buildTargetingDescriptor("automatic", {
      region: ["hanoi"],
      work_mode: ["remote"],
    });
    expect(result.mode).toBe("automatic");
    expect(result.dimensions).toEqual({});
  });

  it("coerces an unknown mode to automatic (broad reach)", () => {
    const result = buildTargetingDescriptor("bogus", { region: ["hanoi"] });
    expect(result.mode).toBe("automatic");
    expect(result.dimensions).toEqual({});
  });

  it("drops a dimension whose values all normalize away", () => {
    const result = buildTargetingDescriptor("manual", {
      region: ["   ", ""],
      industry: ["fintech"],
    });
    expect(result.dimensions.region).toBeUndefined();
    expect(result.dimensions.industry).toEqual(["fintech"]);
  });
});

describe("normalizeDimensionValues — vocab clamping + hygiene", () => {
  it("clamps work_mode to the closed vocabulary", () => {
    expect(normalizeDimensionValues("work_mode", ["remote", "moon", "hybrid"]))
      .toEqual(["remote", "hybrid"]);
  });

  it("clamps student_segment and language to their vocabularies", () => {
    expect(normalizeDimensionValues("student_segment", ["student", "spy"]))
      .toEqual(["student"]);
    expect(normalizeDimensionValues("language", ["vi", "fr", "en"]))
      .toEqual(["vi", "en"]);
  });

  it("lowercases, trims, and de-dupes open tag values", () => {
    expect(normalizeDimensionValues("region", ["  Hanoi ", "hanoi", "HANOI"]))
      .toEqual(["hanoi"]);
  });

  it("caps a dimension at 20 values", () => {
    const many = Array.from({ length: 40 }, (_, i) => `t${i}`);
    expect(normalizeDimensionValues("industry", many)).toHaveLength(20);
  });
});

describe("descriptorFromPlacement — safe read-back", () => {
  it("defaults to automatic for a missing descriptor", () => {
    expect(descriptorFromPlacement(null)).toEqual({
      mode: "automatic",
      dimensions: {},
    });
    expect(descriptorFromPlacement({})).toEqual({
      mode: "automatic",
      dimensions: {},
    });
  });

  it("reads a manual descriptor and strips non-allowlisted keys", () => {
    const placement = {
      targeting: {
        mode: "manual",
        dimensions: {
          region: ["hanoi"],
          email: ["leak@x.com"],
        },
      } as unknown as TargetingDescriptor,
    };
    const result = descriptorFromPlacement(placement);
    expect(result.mode).toBe("manual");
    expect(result.dimensions.region).toEqual(["hanoi"]);
    expect((result.dimensions as Record<string, unknown>).email).toBeUndefined();
  });

  it("preserves a university_restricted descriptor for read-only display", () => {
    const placement = {
      targeting: {
        mode: "university_restricted",
        dimensions: { industry: ["fintech"] },
      } as TargetingDescriptor,
    };
    const result = descriptorFromPlacement(placement);
    expect(result.mode).toBe("university_restricted");
    expect(result.dimensions.industry).toEqual(["fintech"]);
  });
});

describe("isUniversityRestricted", () => {
  it("is true only for the university_restricted mode", () => {
    expect(
      isUniversityRestricted({ mode: "university_restricted", dimensions: {} }),
    ).toBe(true);
    expect(isUniversityRestricted({ mode: "manual", dimensions: {} })).toBe(false);
    expect(isUniversityRestricted({ mode: "automatic", dimensions: {} })).toBe(
      false,
    );
    expect(isUniversityRestricted(null)).toBe(false);
  });
});

describe("activeDimensions / countTargetingValues", () => {
  it("lists only dimensions with values and counts them", () => {
    const desc: TargetingDescriptor = {
      mode: "manual",
      dimensions: { region: ["hanoi", "hcmc"], work_mode: ["remote"] },
    };
    expect(activeDimensions(desc)).toEqual(["region", "work_mode"]);
    expect(countTargetingValues(desc)).toBe(3);
  });

  it("returns empty for a broad-reach descriptor", () => {
    expect(activeDimensions({ mode: "automatic", dimensions: {} })).toEqual([]);
    expect(countTargetingValues({ mode: "automatic", dimensions: {} })).toBe(0);
  });
});
