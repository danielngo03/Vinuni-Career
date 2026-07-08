import { describe, expect, it } from "vitest";
import type { IndustryRoot } from "@/lib/api";
import { industryFilterParamsForSelection } from "@/lib/jobs/industry-filter";

function leaf(id: string, name: string) {
  return {
    id,
    slug: name.toLowerCase().replaceAll(" ", "-"),
    name_vi: name,
    name_en: name,
    level: 2,
    sort_order: 0,
  };
}

function branch(id: string, name: string, children: ReturnType<typeof leaf>[] = []) {
  return {
    id,
    slug: name.toLowerCase().replaceAll(" ", "-"),
    name_vi: name,
    name_en: name,
    level: 1,
    sort_order: 0,
    children,
  };
}

const TREE: IndustryRoot[] = [
  {
    id: "root-tech",
    slug: "technology",
    name_vi: "Công nghệ",
    name_en: "Technology",
    level: 0,
    sort_order: 0,
    children: [
      branch("branch-swe", "Software Engineering", [
        leaf("leaf-frontend", "Frontend"),
        leaf("leaf-backend", "Backend"),
      ]),
      branch("branch-data", "Data", []),
    ],
  },
  {
    id: "root-finance",
    slug: "finance",
    name_vi: "Tài chính",
    name_en: "Finance",
    level: 0,
    sort_order: 1,
    children: [],
  },
];

describe("industryFilterParamsForSelection", () => {
  it("returns industry_group_id for a root-level selection", () => {
    expect(industryFilterParamsForSelection(TREE, ["root-tech"])).toEqual({
      industry_group_id: "root-tech",
    });
  });

  it("returns industry_id for a branch-level selection", () => {
    expect(industryFilterParamsForSelection(TREE, ["branch-swe"])).toEqual({
      industry_id: "branch-swe",
    });
  });

  it("returns specialization_id for a leaf-level selection", () => {
    expect(industryFilterParamsForSelection(TREE, ["leaf-backend"])).toEqual({
      specialization_id: "leaf-backend",
    });
  });

  it("returns no filter when nothing is selected", () => {
    expect(industryFilterParamsForSelection(TREE, [])).toEqual({});
  });

  it("returns no filter (and does not throw) when the id is not found in the tree", () => {
    expect(industryFilterParamsForSelection(TREE, ["unknown-id"])).toEqual({});
  });

  it("returns no filter for an empty tree", () => {
    expect(industryFilterParamsForSelection([], ["root-tech"])).toEqual({});
  });
});
