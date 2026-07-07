import { describe, expect, it } from "vitest";
import type { IndustryRoot } from "@/lib/api/search";
import {
  flattenIndustries,
  findIndustry,
  filterIndustries,
  matchIndustryByName,
  normalize,
} from "@/lib/jobs/industry-lookup";

// ── Fixtures ─────────────────────────────────────────────────────────────────

const TREE: IndustryRoot[] = [
  {
    id: "root-tech",
    slug: "cong-nghe-thong-tin",
    name_vi: "Công nghệ thông tin",
    name_en: "Information Technology",
    level: 0,
    sort_order: 0,
    children: [
      {
        id: "branch-swe",
        slug: "phat-trien-phan-mem",
        name_vi: "Phát triển phần mềm",
        name_en: "Software Development",
        level: 1,
        sort_order: 0,
        children: [
          {
            id: "leaf-frontend",
            slug: "frontend",
            name_vi: "Frontend",
            name_en: "Frontend",
            level: 2,
            sort_order: 0,
          },
          {
            id: "leaf-backend",
            slug: "backend",
            name_vi: "Backend",
            name_en: "Backend",
            level: 2,
            sort_order: 1,
          },
        ],
      },
      {
        id: "branch-data",
        slug: "khoa-hoc-du-lieu",
        name_vi: "Khoa học dữ liệu",
        name_en: "Data Science",
        level: 1,
        sort_order: 1,
        children: [],
      },
    ],
  },
  {
    id: "root-finance",
    slug: "tai-chinh",
    name_vi: "Tài chính",
    name_en: "Finance",
    level: 0,
    sort_order: 1,
    children: [],
  },
];

// ── normalize ─────────────────────────────────────────────────────────────────

describe("normalize", () => {
  it("strips Vietnamese diacritics", () => {
    expect(normalize("Công nghệ")).toBe("cong nghe");
  });
  it("lowercases", () => {
    expect(normalize("Frontend")).toBe("frontend");
  });
  it("collapses whitespace", () => {
    expect(normalize("  a   b  ")).toBe("a b");
  });
});

// ── flattenIndustries ─────────────────────────────────────────────────────────

describe("flattenIndustries", () => {
  const flat = flattenIndustries(TREE);

  it("includes all nodes (root + branch + leaf)", () => {
    const ids = flat.map((n) => n.id);
    expect(ids).toContain("root-tech");
    expect(ids).toContain("branch-swe");
    expect(ids).toContain("leaf-frontend");
    expect(ids).toContain("leaf-backend");
    expect(ids).toContain("branch-data");
    expect(ids).toContain("root-finance");
    expect(flat).toHaveLength(6);
  });

  it("builds correct English path for a leaf", () => {
    const node = flat.find((n) => n.id === "leaf-frontend")!;
    expect(node.pathEn).toBe(
      "Information Technology › Software Development › Frontend",
    );
  });

  it("builds correct Vietnamese path for a leaf", () => {
    const node = flat.find((n) => n.id === "leaf-frontend")!;
    expect(node.pathVi).toBe(
      "Công nghệ thông tin › Phát triển phần mềm › Frontend",
    );
  });

  it("branch path has root › branch format", () => {
    const node = flat.find((n) => n.id === "branch-swe")!;
    expect(node.pathEn).toBe("Information Technology › Software Development");
  });

  it("root path equals root name only", () => {
    const node = flat.find((n) => n.id === "root-tech")!;
    expect(node.pathEn).toBe("Information Technology");
  });

  it("search field is normalized (diacritics stripped + lowercased)", () => {
    const node = flat.find((n) => n.id === "root-tech")!;
    expect(node.search).toContain("cong nghe thong tin");
    expect(node.search).toContain("information technology");
  });

  it("handles empty roots array", () => {
    expect(flattenIndustries([])).toEqual([]);
  });

  it("handles branches with no children", () => {
    const node = flat.find((n) => n.id === "branch-data")!;
    expect(node.pathEn).toBe("Information Technology › Data Science");
  });
});

// ── findIndustry ──────────────────────────────────────────────────────────────

describe("findIndustry", () => {
  const flat = flattenIndustries(TREE);

  it("finds an existing node by id", () => {
    expect(findIndustry(flat, "leaf-frontend")?.name_en).toBe("Frontend");
  });
  it("returns null for unknown id", () => {
    expect(findIndustry(flat, "unknown")).toBeNull();
  });
  it("returns null for null input", () => {
    expect(findIndustry(flat, null)).toBeNull();
  });
  it("returns null for undefined input", () => {
    expect(findIndustry(flat, undefined)).toBeNull();
  });
});

// ── filterIndustries ──────────────────────────────────────────────────────────

describe("filterIndustries", () => {
  const flat = flattenIndustries(TREE);

  it("returns all nodes (capped) when query is empty", () => {
    const result = filterIndustries(flat, "");
    expect(result.length).toBeGreaterThan(0);
    expect(result.length).toBeLessThanOrEqual(200);
  });

  it("matches by English name substring", () => {
    const result = filterIndustries(flat, "frontend");
    expect(result.map((n) => n.id)).toContain("leaf-frontend");
  });

  it("matches by Vietnamese diacritic-stripped name", () => {
    // "Tai chinh" -> "Tài chính"
    const result = filterIndustries(flat, "Tai chinh");
    expect(result.map((n) => n.id)).toContain("root-finance");
  });

  it("matches parent path when querying a parent segment", () => {
    // "Software" should hit branch and its leaves via path matching
    const result = filterIndustries(flat, "software");
    const ids = result.map((n) => n.id);
    expect(ids).toContain("branch-swe");
  });

  it("returns empty array when nothing matches", () => {
    const result = filterIndustries(flat, "zzznomatch");
    expect(result).toHaveLength(0);
  });
});

// ── matchIndustryByName ───────────────────────────────────────────────────────

describe("matchIndustryByName", () => {
  const flat = flattenIndustries(TREE);

  it("exact English name match returns the correct node", () => {
    const match = matchIndustryByName("Software Development", flat);
    expect(match?.id).toBe("branch-swe");
  });

  it("prefers leaf over branch on equal token match (deeper level wins)", () => {
    // "Frontend" is an exact match and a leaf (level 2)
    const match = matchIndustryByName("Frontend", flat);
    expect(match?.id).toBe("leaf-frontend");
    expect(match?.level).toBe(2);
  });

  it("matches via diacritic-stripped Vietnamese name", () => {
    const match = matchIndustryByName("Phat trien phan mem", flat);
    expect(match?.id).toBe("branch-swe");
  });

  it("returns null for null input", () => {
    expect(matchIndustryByName(null, flat)).toBeNull();
  });

  it("returns null for blank string", () => {
    expect(matchIndustryByName("   ", flat)).toBeNull();
  });

  it("returns null when no token overlap exists", () => {
    expect(matchIndustryByName("XyzZzNoMatch", flat)).toBeNull();
  });

  it("partial token match falls back to substring score", () => {
    // "Data" should match "Data Science" branch
    const match = matchIndustryByName("Data", flat);
    expect(match?.id).toBe("branch-data");
  });
});
