/**
 * Interview readiness view — pure logic tests (vitest env `node`, no DOM).
 *
 * The load-bearing contract is the HONEST low-data state: below the backend's
 * minimum evaluated answers the readiness is `not_enough_data` with a null
 * percentage, and the view must NEVER surface a fabricated number — it exposes
 * `hasSignal: false` + `answersNeeded` so the UI can say "practise N more".
 */
import { describe, it, expect } from "vitest";
import type { InterviewReadiness } from "@/lib/api/interview-prep";
import {
  interviewReadinessView,
  readinessBandTone,
} from "@/lib/jobs/interview-readiness";

function readiness(overrides: Partial<InterviewReadiness> = {}): InterviewReadiness {
  return {
    status: "ready_signal",
    attempts: 3,
    answers_evaluated: 9,
    readiness_pct: 72,
    band: "progressing",
    trend: "improving",
    answers_needed: 0,
    ...overrides,
  };
}

describe("interviewReadinessView — honest low-data state", () => {
  it("hides the number and reports answersNeeded when not enough data", () => {
    const view = interviewReadinessView(
      readiness({
        status: "not_enough_data",
        readiness_pct: null,
        band: null,
        trend: null,
        answers_evaluated: 1,
        answers_needed: 2,
        attempts: 1,
      }),
    );
    expect(view.hasSignal).toBe(false);
    // No fabricated readiness number is ever derived.
    expect(view.pct).toBeNull();
    expect(view.fillPct).toBe(0);
    expect(view.band).toBeNull();
    expect(view.trend).toBeNull();
    expect(view.answersNeeded).toBe(2);
    expect(view.tone).toBe("low");
  });

  it("treats a ready_signal status with a null pct as low-data (defensive)", () => {
    const view = interviewReadinessView(
      readiness({ status: "ready_signal", readiness_pct: null }),
    );
    expect(view.hasSignal).toBe(false);
    expect(view.pct).toBeNull();
  });
});

describe("interviewReadinessView — real signal", () => {
  it("surfaces the masked pct, band, trend, and a clamped fill", () => {
    const view = interviewReadinessView(readiness({ readiness_pct: 72 }));
    expect(view.hasSignal).toBe(true);
    expect(view.pct).toBe(72);
    expect(view.fillPct).toBe(72);
    expect(view.band).toBe("progressing");
    expect(view.trend).toBe("improving");
    expect(view.tone).toBe("ok");
  });

  it("clamps an out-of-range pct fill to 0..100", () => {
    expect(interviewReadinessView(readiness({ readiness_pct: 140 })).fillPct).toBe(100);
    expect(interviewReadinessView(readiness({ readiness_pct: -5 })).fillPct).toBe(0);
  });
});

describe("readinessBandTone", () => {
  it("maps bands to coarse tones (never color-only in the UI)", () => {
    expect(readinessBandTone("interview_ready")).toBe("ok");
    expect(readinessBandTone("progressing")).toBe("ok");
    expect(readinessBandTone("emerging")).toBe("progress");
    expect(readinessBandTone("developing")).toBe("low");
    expect(readinessBandTone(null)).toBe("low");
  });
});
