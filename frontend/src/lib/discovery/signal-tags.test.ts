import { describe, expect, it } from "vitest";
import type { CompanyDetail, EventSummary, JobSummary } from "@/lib/api";
import {
  companySignalTags,
  eventSignalTags,
  jobSignalTags,
} from "@/lib/discovery/signal-tags";

/**
 * These tests are the privacy guardrail for the discovery signals emitted by
 * the public marketplace surfaces. They assert (a) the coarse taxonomy keys the
 * ranker waits for are produced from available data, and (b) NOTHING outside the
 * backend allowlist (`discovery/domain/allowlist.py`) — and in particular no PII
 * or opaque UUID-as-taxonomy — is ever produced.
 */

// The ONLY keys the backend allowlist persists. `device_type` is attached later
// by the analytics client, not by these builders.
const ALLOWED_KEYS = new Set([
  "search_terms",
  "categories",
  "industries",
  "role_families",
  "company_ids",
  "event_ids",
  "work_mode",
  "city",
]);

// A representative slice of the forbidden set — none of these may ever appear.
const FORBIDDEN_KEYS = [
  "name",
  "full_name",
  "email",
  "phone",
  "user_id",
  "ip",
  "gps",
  "geo",
  "latitude",
  "longitude",
  "exact_location",
  "address",
  "cv_text",
  "resume",
  "gender",
  "salary",
  "ad_id",
  "gclid",
  "fingerprint",
  "device_id",
  "industry_id",
  "org_id",
  "title",
  "description",
];

function expectAllowlistedOnly(tags: Record<string, unknown>) {
  for (const key of Object.keys(tags)) {
    expect(ALLOWED_KEYS, `unexpected key "${key}"`).toContain(key);
  }
  for (const forbidden of FORBIDDEN_KEYS) {
    expect(tags, `forbidden key "${forbidden}" present`).not.toHaveProperty(forbidden);
  }
}

const ORG_ID = "3f1a5e00-0000-4000-8000-000000000001";
const JOB_ID = "3f1a5e00-0000-4000-8000-0000000000aa";
const EVENT_ID = "3f1a5e00-0000-4000-8000-0000000000bb";
const COMPANY_ID = "3f1a5e00-0000-4000-8000-0000000000cc";

function baseJob(overrides: Partial<JobSummary> = {}): JobSummary {
  return {
    id: JOB_ID,
    org_id: ORG_ID,
    title: "Senior Backend Engineer",
    slug: "senior-backend-engineer",
    employment_type: "full_time",
    employment_type_label: "Full time",
    location_type: "hybrid",
    location_type_label: "Hybrid",
    location_city: "Hanoi",
    location_country: "VN",
    locations: [],
    required_skills: ["python", "postgres"],
    salary: null,
    salary_display: { kind: "negotiable", label: "", min: null, max: null, currency: "VND" },
    experience_display: { kind: "no_requirement", label: "", min: null, max: null },
    is_featured: false,
    is_sponsored: false,
    application_deadline: null,
    published_at: null,
    ...overrides,
  } as JobSummary;
}

describe("jobSignalTags", () => {
  it("emits only allowlisted coarse keys and no PII / UUID-as-taxonomy", () => {
    const tags = jobSignalTags(baseJob());
    expectAllowlistedOnly(tags as Record<string, unknown>);
    expect(tags.company_ids).toEqual([ORG_ID]);
    expect(tags.work_mode).toBe("hybrid");
    expect(tags.city).toBe("Hanoi");
  });

  it("emits role_families + industries once the backend projection stamps them", () => {
    const tags = jobSignalTags(
      baseJob({ role_family: "software_engineering", industry_slug: "information-technology" }),
    );
    expectAllowlistedOnly(tags as Record<string, unknown>);
    expect(tags.role_families).toEqual(["software_engineering"]);
    expect(tags.industries).toEqual(["information-technology"]);
  });

  it("omits taxonomy keys entirely when the job carries no role/industry (honest)", () => {
    const tags = jobSignalTags(baseJob());
    expect(tags).not.toHaveProperty("role_families");
    expect(tags).not.toHaveProperty("industries");
    expect(tags).not.toHaveProperty("categories");
  });

  it("carries the active search query as a coarse search term when provided", () => {
    const tags = jobSignalTags(baseJob(), { searchTerms: ["backend", "  backend  "] });
    expectAllowlistedOnly(tags as Record<string, unknown>);
    // De-duped + trimmed.
    expect(tags.search_terms).toEqual(["backend"]);
  });

  it("drops an invalid work_mode rather than emitting a non-coarse value", () => {
    const tags = jobSignalTags(baseJob({ location_type: "somewhere_specific" }));
    expect(tags).not.toHaveProperty("work_mode");
  });

  it("omits city when the job has no coarse city", () => {
    const tags = jobSignalTags(baseJob({ location_city: null }));
    expect(tags).not.toHaveProperty("city");
  });

  it("never emits the raw job title, org_id key, or description", () => {
    const tags = jobSignalTags(baseJob()) as Record<string, unknown>;
    expect(tags).not.toHaveProperty("title");
    expect(Object.values(tags).flat()).not.toContain("Senior Backend Engineer");
  });
});

describe("eventSignalTags", () => {
  const event = {
    id: EVENT_ID,
    event_type: "career_fair",
  } as EventSummary;

  it("emits the event id + coarse event category, nothing else", () => {
    const tags = eventSignalTags(event);
    expectAllowlistedOnly(tags as Record<string, unknown>);
    expect(tags.event_ids).toEqual([EVENT_ID]);
    expect(tags.categories).toEqual(["career_fair"]);
  });

  it("omits categories when event_type is blank", () => {
    const tags = eventSignalTags({ id: EVENT_ID, event_type: "" } as EventSummary);
    expect(tags.event_ids).toEqual([EVENT_ID]);
    expect(tags).not.toHaveProperty("categories");
  });
});

describe("companySignalTags", () => {
  it("emits the company id + coarse industry, nothing else", () => {
    const tags = companySignalTags({
      id: COMPANY_ID,
      industry: "Information Technology",
    } as CompanyDetail);
    expectAllowlistedOnly(tags as Record<string, unknown>);
    expect(tags.company_ids).toEqual([COMPANY_ID]);
    expect(tags.industries).toEqual(["Information Technology"]);
  });

  it("omits industries when the company has none (honest)", () => {
    const tags = companySignalTags({ id: COMPANY_ID, industry: null } as CompanyDetail);
    expect(tags.company_ids).toEqual([COMPANY_ID]);
    expect(tags).not.toHaveProperty("industries");
  });
});
