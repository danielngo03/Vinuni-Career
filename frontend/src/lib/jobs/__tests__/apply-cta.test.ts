/**
 * Apply CTA state — pure logic tests (vitest env `node`, no DOM).
 *
 * Load-bearing contract: when the student's own apply-readiness says
 * `already_applied`, the job-detail Apply button must be DISABLED and relabelled
 * ("Đã ứng tuyển"), never inviting a duplicate the backend would reject with a
 * `409 duplicate_application`.
 */
import { describe, it, expect } from "vitest";
import { deriveApplyCta } from "@/lib/jobs/job-intelligence";

const base = {
  isHydrating: false,
  isGuest: false,
  canApply: true,
  alreadyApplied: false,
  deadlinePassed: false,
};

describe("deriveApplyCta", () => {
  it("disables + relabels the button when already applied", () => {
    const cta = deriveApplyCta({ ...base, alreadyApplied: true });
    expect(cta.label).toBe("alreadyApplied");
    expect(cta.disabled).toBe(true);
    expect(cta.showViewApplications).toBe(true);
  });

  it("disables the button when the deadline has passed", () => {
    const cta = deriveApplyCta({ ...base, deadlinePassed: true });
    expect(cta.label).toBe("deadlinePassed");
    expect(cta.disabled).toBe(true);
    expect(cta.showViewApplications).toBe(false);
  });

  it("already-applied wins over a passed deadline", () => {
    const cta = deriveApplyCta({
      ...base,
      alreadyApplied: true,
      deadlinePassed: true,
    });
    expect(cta.label).toBe("alreadyApplied");
  });

  it("is an enabled apply CTA for a ready student", () => {
    const cta = deriveApplyCta(base);
    expect(cta.label).toBe("apply");
    expect(cta.disabled).toBe(false);
    expect(cta.showViewApplications).toBe(false);
  });

  it("shows the sign-in label for a guest (enabled → opens login)", () => {
    const cta = deriveApplyCta({ ...base, isGuest: true, canApply: false });
    expect(cta.label).toBe("signIn");
    expect(cta.disabled).toBe(false);
  });

  it("shows a disabled students-only label for a non-student", () => {
    const cta = deriveApplyCta({ ...base, canApply: false });
    expect(cta.label).toBe("studentsOnly");
    expect(cta.disabled).toBe(true);
  });

  it("shows a disabled loading label while auth hydrates", () => {
    const cta = deriveApplyCta({ ...base, isHydrating: true });
    expect(cta.label).toBe("loading");
    expect(cta.disabled).toBe(true);
  });
});
