import { describe, expect, it } from "vitest";
import { formatSalary, jobSalaryLabel } from "@/lib/jobs/format";

describe("formatSalary", () => {
  it("returns null when salary is undisclosed", () => {
    expect(formatSalary(null, "vi")).toBeNull();
    expect(formatSalary({ min: null, max: null, currency: "VND" }, "vi")).toBeNull();
  });

  it("formats a VND range (vi locale)", () => {
    expect(
      formatSalary({ min: 30_000_000, max: 60_000_000, currency: "VND" }, "vi"),
    ).toBe("30 - 60 triệu");
  });

  it("formats a single min ('Từ X') in vi locale", () => {
    expect(formatSalary({ min: 20_000_000, max: null, currency: "VND" }, "vi")).toBe(
      "Từ 20 triệu",
    );
  });

  it("formats a single min ('From X') in en locale", () => {
    expect(formatSalary({ min: 20_000_000, max: null, currency: "VND" }, "en")).toBe(
      "From 20 M VND",
    );
  });

  it("formats a single max ('Tới X') in vi locale", () => {
    expect(formatSalary({ min: null, max: 50_000_000, currency: "VND" }, "vi")).toBe(
      "Tới 50 triệu",
    );
  });

  it("formats a single max ('Up to X') in en locale", () => {
    expect(formatSalary({ min: null, max: 50_000_000, currency: "VND" }, "en")).toBe(
      "Up to 50 M VND",
    );
  });

  it("collapses equal min/max to a single figure", () => {
    expect(
      formatSalary({ min: 25_000_000, max: 25_000_000, currency: "VND" }, "vi"),
    ).toBe("25 triệu");
  });

  it("formats non-VND currency with the raw currency code", () => {
    expect(formatSalary({ min: 1000, max: 2000, currency: "USD" }, "en")).toBe(
      "1,000 - 2,000 USD",
    );
  });

  it("formats non-VND currency in vi locale number formatting", () => {
    expect(formatSalary({ min: 1000, max: 2000, currency: "USD" }, "vi")).toBe(
      "1.000 - 2.000 USD",
    );
  });
});

describe("jobSalaryLabel", () => {
  it("prefers the server-authoritative salary_display.label, e.g. negotiable", () => {
    expect(
      jobSalaryLabel(
        {
          salary: null,
          salary_display: { label: "Thỏa thuận" },
        },
        "vi",
      ),
    ).toBe("Thỏa thuận");
  });

  it("prefers salary_display.label over re-deriving from salary even when both present", () => {
    expect(
      jobSalaryLabel(
        {
          salary: { min: 10_000_000, max: 20_000_000, currency: "VND" },
          salary_display: { label: "10 - 20 triệu" },
        },
        "vi",
      ),
    ).toBe("10 - 20 triệu");
  });

  it("falls back to formatSalary() when salary_display is absent (legacy rows)", () => {
    expect(
      jobSalaryLabel(
        { salary: { min: 10_000_000, max: 20_000_000, currency: "VND" } },
        "vi",
      ),
    ).toBe("10 - 20 triệu");
  });

  it("returns null when neither salary_display nor salary is present", () => {
    expect(jobSalaryLabel({ salary: null }, "vi")).toBeNull();
  });
});
