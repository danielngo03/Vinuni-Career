import type { IndustryBranch, IndustryLeaf, IndustryRoot } from "@/lib/api";

export type IndustryNode = IndustryRoot | IndustryBranch | IndustryLeaf;

/** Canonical single-select industry query params consumed by `GET /jobs`. */
export type IndustryFilterParams =
  | { industry_group_id: string }
  | { industry_id: string }
  | { specialization_id: string }
  | Record<string, never>;

/**
 * Resolve a single selected industry node id to the canonical level-scoped
 * query param the public jobs endpoint expects (`industry_group_id` for a
 * root node, `industry_id` for a branch node, `specialization_id` for a leaf
 * node). Returns `{}` when there is no selection or the id is not present in
 * the tree — callers must not throw or send a stale/free-text filter.
 */
export function industryFilterParamsForSelection(
  roots: IndustryRoot[],
  selectedIds: string[],
): IndustryFilterParams {
  const selectedId = selectedIds[0];
  if (!selectedId) return {};

  for (const root of roots) {
    if (root.id === selectedId) return { industry_group_id: root.id };
    for (const branch of root.children) {
      if (branch.id === selectedId) return { industry_id: branch.id };
      for (const leaf of branch.children) {
        if (leaf.id === selectedId) return { specialization_id: leaf.id };
      }
    }
  }

  return {};
}
