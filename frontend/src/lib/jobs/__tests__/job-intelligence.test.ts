import { describe, expect, it } from "vitest";
import {
  competitionRows,
  competitionTone,
  deriveCvReadiness,
  drawerQueryEnabled,
  energyGate,
  hasCompetitionSignal,
  improvementIdempotencyKey,
  isKnownBand,
  isStudentViewer,
} from "@/lib/jobs/job-intelligence";
import type {
  StudentApplyReadiness,
  StudentCompetitionIntelligence,
  StudentJobFit,
} from "@/lib/api/jobs";
import type { AiEnergyUsage } from "@/lib/api/ai-assistant";

/* -------------------------------------------------------------------------- */
/* Guest gate — guests / non-students never see fit or competition            */
/* -------------------------------------------------------------------------- */

describe("isStudentViewer", () => {
  it("is true only for an authenticated student", () => {
    expect(isStudentViewer("authenticated", "student")).toBe(true);
  });

  it("is false for a guest", () => {
    expect(isStudentViewer("guest", "student")).toBe(false);
    expect(isStudentViewer("guest", null)).toBe(false);
  });

  it("is false for authenticated non-student personas", () => {
    expect(isStudentViewer("authenticated", "partner")).toBe(false);
    expect(isStudentViewer("authenticated", "university")).toBe(false);
    expect(isStudentViewer("authenticated", null)).toBe(false);
  });

  it("is false while auth is still hydrating", () => {
    expect(isStudentViewer("unknown", "student")).toBe(false);
  });
});

/* -------------------------------------------------------------------------- */
/* Score-only default — drawers fetch ONLY when open                          */
/* -------------------------------------------------------------------------- */

describe("drawerQueryEnabled (on-demand fetch gating)", () => {
  it("is disabled while the drawer is closed (mount / default job detail)", () => {
    // This is the `enabled` flag both the Analyze and Competition drawer
    // queries use, so a closed drawer provably fires neither the fit-explanation
    // nor the competition-explanation model call on the default score-only load.
    expect(drawerQueryEnabled(false)).toBe(false);
  });

  it("is enabled exactly when the drawer opens", () => {
    expect(drawerQueryEnabled(true)).toBe(true);
  });
});

/* -------------------------------------------------------------------------- */
/* Competition — honest bands, no fabrication, no raw counts                   */
/* -------------------------------------------------------------------------- */

function baseCompetition(
  over: Partial<StudentCompetitionIntelligence> = {},
): StudentCompetitionIntelligence {
  return {
    score: 42,
    label: "moderate",
    signal: "ok",
    basis: "applicant_caliber",
    seats_bucket: "single_seat",
    application_volume_bucket: "high",
    applicants_per_seat_band: "high",
    strong_competitor_density: "some",
    applicant_quality_bucket: "mixed",
    student_standing_bucket: "middle_of_pack",
    standing_vs_strong: "among",
    student_fit_bucket: "competitive",
    deadline_freshness: "closing_soon",
    source_mix: null,
    guidance: [],
    ...over,
  };
}

describe("isKnownBand", () => {
  it("treats unknown/low_signal/null as not-known", () => {
    expect(isKnownBand("unknown")).toBe(false);
    expect(isKnownBand("low_signal")).toBe(false);
    expect(isKnownBand(null)).toBe(false);
    expect(isKnownBand(undefined)).toBe(false);
  });

  it("treats any real band value as known", () => {
    expect(isKnownBand("high")).toBe(true);
    expect(isKnownBand("few")).toBe(true);
    expect(isKnownBand("ahead")).toBe(true);
  });
});

describe("hasCompetitionSignal", () => {
  it("is false when the pool is below threshold (low_signal)", () => {
    expect(
      hasCompetitionSignal(baseCompetition({ signal: "low_signal", label: null })),
    ).toBe(false);
  });

  it("is false when no level label was produced", () => {
    expect(hasCompetitionSignal(baseCompetition({ label: null }))).toBe(false);
  });

  it("is true when there is a real level", () => {
    expect(hasCompetitionSignal(baseCompetition())).toBe(true);
  });
});

describe("competitionRows (honest rendering)", () => {
  it("drops unknown/low_signal bands but always keeps deadline", () => {
    const rows = competitionRows(
      baseCompetition({
        applicants_per_seat_band: "low_signal",
        strong_competitor_density: "low_signal",
        standing_vs_strong: "low_signal",
        applicant_quality_bucket: "unknown",
        deadline_freshness: "no_deadline",
      }),
    );
    // Only the always-known deadline row survives — no fabricated caliber rows.
    expect(rows).toEqual([{ key: "deadline", value: "no_deadline" }]);
  });

  it("renders every known band in priority order", () => {
    const rows = competitionRows(baseCompetition());
    expect(rows.map((r) => r.key)).toEqual([
      "applicants_per_seat",
      "strong_density",
      "standing_vs_strong",
      "applicant_quality",
      "deadline",
    ]);
  });

  it("never emits a raw count — only coarse band values", () => {
    const rows = competitionRows(baseCompetition());
    for (const r of rows) {
      expect(typeof r.value).toBe("string");
      expect(r.value).not.toMatch(/^\d+$/);
    }
  });
});

describe("competitionTone", () => {
  it("maps very_high onto the high (pressure) tone", () => {
    expect(competitionTone("very_high")).toBe("high");
    expect(competitionTone("high")).toBe("high");
    expect(competitionTone("moderate")).toBe("moderate");
    expect(competitionTone("low")).toBe("low");
  });
});

/* -------------------------------------------------------------------------- */
/* CV readiness (WS-15) — derived, terminal states win                        */
/* -------------------------------------------------------------------------- */

function fit(over: Partial<StudentJobFit> = {}): StudentJobFit {
  return {
    status: "scored",
    score: 85,
    label: "strong_fit",
    bands: {
      skills: 90,
      experience: 80,
      scope: 70,
      credentials: 60,
      soft_skills: 75,
      trajectory: 65,
    },
    matched_evidence: [],
    gaps: [],
    improvement_actions: [],
    signal: "ok",
    stale: false,
    explanation: null,
    ...over,
  };
}

function readiness(
  over: Partial<StudentApplyReadiness> = {},
): StudentApplyReadiness {
  return {
    ready: true,
    blocked_reason: null,
    already_applied: false,
    deadline_passed: false,
    has_active_cv: true,
    ...over,
  };
}

describe("deriveCvReadiness", () => {
  it("no_cv wins when there is no active CV", () => {
    const r = deriveCvReadiness(fit({ status: "no_active_cv", score: null }), readiness({ has_active_cv: false }));
    expect(r.level).toBe("no_cv");
    expect(r.score).toBeNull();
    expect(r.actionable).toBe(false);
  });

  it("already-applied is a terminal state over the score band", () => {
    const r = deriveCvReadiness(fit(), readiness({ already_applied: true, ready: false }));
    expect(r.level).toBe("applied");
    expect(r.actionable).toBe(false);
  });

  it("deadline-passed is a terminal state", () => {
    const r = deriveCvReadiness(fit(), readiness({ deadline_passed: true, ready: false }));
    expect(r.level).toBe("closed");
  });

  it("a strong fresh CV reads ready", () => {
    expect(deriveCvReadiness(fit({ score: 88 }), readiness()).level).toBe("ready");
  });

  it("a strong but stale CV is only nearly ready", () => {
    expect(deriveCvReadiness(fit({ score: 88, stale: true }), readiness()).level).toBe("almost");
  });

  it("a mid score reads almost; a low score needs work", () => {
    expect(deriveCvReadiness(fit({ score: 60 }), readiness()).level).toBe("almost");
    expect(deriveCvReadiness(fit({ score: 30 }), readiness()).level).toBe("needs_work");
  });
});

/* -------------------------------------------------------------------------- */
/* Energy gate — masked % only, never tokens/USD                              */
/* -------------------------------------------------------------------------- */

function usage(over: Partial<AiEnergyUsage> = {}): AiEnergyUsage {
  return {
    scope: "user",
    energy_pct: 64,
    weekly: { used: 36, allowance: 100, wallet: 0, capacity: 100 },
    session_3h: { used: 2, soft_cap: 20, over_soft_cap: false },
    blocked: false,
    blocked_reason: null,
    warning: false,
    warning_reason: null,
    week_reset: "2026-07-15T00:00:00Z",
    ...over,
  };
}

describe("energyGate", () => {
  it("returns null before usage loads", () => {
    expect(energyGate(undefined)).toBeNull();
  });

  it("exposes only a rounded remaining percentage + coarse tone", () => {
    const g = energyGate(usage({ energy_pct: 63.6 }))!;
    expect(g.pct).toBe(64);
    expect(g.tone).toBe("ok");
    expect(g.blocked).toBe(false);
    // No token/USD/provider fields leak through.
    expect(Object.keys(g).sort()).toEqual(["blocked", "pct", "tone"]);
  });

  it("reports blocked when weekly energy is exhausted", () => {
    const g = energyGate(usage({ blocked: true, energy_pct: 0 }))!;
    expect(g.blocked).toBe(true);
    expect(g.tone).toBe("block");
  });

  it("warns on a low remaining balance", () => {
    expect(energyGate(usage({ energy_pct: 12 }))!.tone).toBe("warn");
  });
});

describe("improvementIdempotencyKey", () => {
  it("is stable + slugged per (cv, skill) so a retry de-dupes", () => {
    expect(improvementIdempotencyKey("cv-1", "React Native")).toBe(
      "job-fit-improve:cv-1:react-native",
    );
    expect(improvementIdempotencyKey("cv-1", "React Native")).toBe(
      improvementIdempotencyKey("cv-1", "React Native"),
    );
  });

  it("differs across CVs and skills", () => {
    expect(improvementIdempotencyKey("cv-1", "SQL")).not.toBe(
      improvementIdempotencyKey("cv-2", "SQL"),
    );
    expect(improvementIdempotencyKey("cv-1", "SQL")).not.toBe(
      improvementIdempotencyKey("cv-1", "Go"),
    );
  });
});
