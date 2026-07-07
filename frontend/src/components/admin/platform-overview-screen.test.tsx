/**
 * Platform Overview screen — pure helper unit tests.
 *
 * The vitest environment is `node` (no DOM), so we test pure functions only:
 * `outboxTone`, `outboxToneToStatusTone`.
 *
 * These helpers drive the outbox health badge tonal logic on the platform
 * overview landing. Testing them at the threshold boundaries gives confidence
 * that healthy / pending / failed states are classified correctly.
 */
import { describe, it, expect } from "vitest";
import { outboxTone, outboxToneToStatusTone } from "./overview-helpers";

/* -------------------------------------------------------------------------- */
/* outboxTone — healthy / pending / failed thresholds                         */
/* -------------------------------------------------------------------------- */

describe("outboxTone", () => {
  it("returns active when pending=0 and failed=0 (all clear)", () => {
    expect(outboxTone(0, 0)).toBe("active");
  });

  it("returns pending when pending>0 and failed=0", () => {
    expect(outboxTone(1, 0)).toBe("pending");
    expect(outboxTone(100, 0)).toBe("pending");
  });

  it("returns rejected when failed_last_hour>0 regardless of pending", () => {
    expect(outboxTone(0, 1)).toBe("rejected");
    expect(outboxTone(5, 3)).toBe("rejected");
    expect(outboxTone(0, 100)).toBe("rejected");
  });

  it("prioritises rejected over pending (failed > 0 wins)", () => {
    expect(outboxTone(10, 2)).toBe("rejected");
  });

  it("returns active for non-finite inputs (safe fallback)", () => {
    expect(outboxTone(NaN, 0)).toBe("active");
    expect(outboxTone(0, NaN)).toBe("active");
    expect(outboxTone(Infinity, 0)).toBe("active");
  });
});

/* -------------------------------------------------------------------------- */
/* outboxToneToStatusTone — maps to StatusBadge StatusTone                    */
/* -------------------------------------------------------------------------- */

describe("outboxToneToStatusTone", () => {
  it("maps active to active", () => {
    expect(outboxToneToStatusTone("active")).toBe("active");
  });

  it("maps pending to pending", () => {
    expect(outboxToneToStatusTone("pending")).toBe("pending");
  });

  it("maps rejected to rejected", () => {
    expect(outboxToneToStatusTone("rejected")).toBe("rejected");
  });
});
