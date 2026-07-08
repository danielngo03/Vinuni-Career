/**
 * Campaign-analytics state helpers — pure unit tests.
 *
 * Focus: the empty state and the not-authorized (cross-org 404 / 403 / 401)
 * derivation the drawer + overview render, and the aggregate formatting.
 */
import { describe, it, expect } from "vitest";
import { ApiError } from "@/lib/api";
import type { OrgAnalytics, PlacementAnalytics } from "@/lib/api";
import {
  analyticsErrorKind,
  countersAreEmpty,
  formatRatePct,
  isOrgAnalyticsEmpty,
  isPlacementAnalyticsEmpty,
  impressionsSeries,
} from "./analytics";

const ZERO = {
  impressions: 0,
  clicks: 0,
  views: 0,
  apply_starts: 0,
  save_intents: 0,
  event_register_intents: 0,
};

function apiError(status: number, code = "RESOURCE_NOT_FOUND"): ApiError {
  return new ApiError({ code: code as never, message: "x", status });
}

describe("analyticsErrorKind — not-authorized mapping", () => {
  it("maps a cross-org 404 to notAuthorized (never confirms existence)", () => {
    expect(analyticsErrorKind(apiError(404))).toBe("notAuthorized");
  });

  it("maps 403 and 401 to notAuthorized", () => {
    expect(analyticsErrorKind(apiError(403, "PERMISSION_DENIED"))).toBe(
      "notAuthorized",
    );
    expect(analyticsErrorKind(apiError(401, "AUTH_REQUIRED"))).toBe(
      "notAuthorized",
    );
  });

  it("maps a 500 / unknown to a retryable error", () => {
    expect(analyticsErrorKind(apiError(500, "INTERNAL_ERROR"))).toBe("error");
    expect(analyticsErrorKind(new Error("boom"))).toBe("error");
    expect(analyticsErrorKind(null)).toBe("error");
  });
});

describe("countersAreEmpty", () => {
  it("is true for all-zero counters and nullish", () => {
    expect(countersAreEmpty(ZERO)).toBe(true);
    expect(countersAreEmpty(null)).toBe(true);
    expect(countersAreEmpty(undefined)).toBe(true);
  });

  it("is false when any counter has signal", () => {
    expect(countersAreEmpty({ ...ZERO, clicks: 1 })).toBe(false);
  });
});

describe("isPlacementAnalyticsEmpty", () => {
  it("is true with no daily rows and zero totals", () => {
    const a: PlacementAnalytics = {
      placement_id: "p1",
      org_id: "o1",
      totals: { ...ZERO },
      ctr_pct: null,
      apply_start_rate_pct: null,
      cost_per_apply_start: null,
      campaign_price: "1500000.00",
      currency: "VND",
      daily: [],
      day_count: 0,
      note: "n",
    };
    expect(isPlacementAnalyticsEmpty(a)).toBe(true);
    expect(isPlacementAnalyticsEmpty(null)).toBe(true);
  });

  it("is false once there is measured activity", () => {
    const a: PlacementAnalytics = {
      placement_id: "p1",
      org_id: "o1",
      totals: { ...ZERO, impressions: 120, clicks: 6 },
      ctr_pct: 5,
      apply_start_rate_pct: 1.7,
      cost_per_apply_start: "750000.00",
      campaign_price: "1500000.00",
      currency: "VND",
      daily: [
        { date: "2026-07-01", ...ZERO, impressions: 120, clicks: 6, ctr_pct: 5 },
      ],
      day_count: 1,
      note: "n",
    };
    expect(isPlacementAnalyticsEmpty(a)).toBe(false);
    expect(impressionsSeries(a)).toEqual([120]);
  });
});

describe("isOrgAnalyticsEmpty", () => {
  it("is true with zero campaigns", () => {
    const o: OrgAnalytics = {
      org_id: "o1",
      campaign_count: 0,
      totals: { ...ZERO },
      ctr_pct: null,
      apply_start_rate_pct: null,
      campaigns: [],
      note: "n",
    };
    expect(isOrgAnalyticsEmpty(o)).toBe(true);
    expect(isOrgAnalyticsEmpty(null)).toBe(true);
  });

  it("is false with campaigns and signal", () => {
    const o: OrgAnalytics = {
      org_id: "o1",
      campaign_count: 1,
      totals: { ...ZERO, impressions: 10 },
      ctr_pct: 0,
      apply_start_rate_pct: 0,
      campaigns: [{ placement_id: "p1", ...ZERO, impressions: 10, ctr_pct: 0 }],
      note: "n",
    };
    expect(isOrgAnalyticsEmpty(o)).toBe(false);
  });
});

describe("formatRatePct", () => {
  it("formats a number to one decimal with a percent sign", () => {
    expect(formatRatePct(5)).toBe("5.0%");
    expect(formatRatePct(1.73)).toBe("1.7%");
  });

  it("renders a dash for null / NaN", () => {
    expect(formatRatePct(null)).toBe("—");
    expect(formatRatePct(undefined)).toBe("—");
    expect(formatRatePct(Number.NaN)).toBe("—");
  });
});
