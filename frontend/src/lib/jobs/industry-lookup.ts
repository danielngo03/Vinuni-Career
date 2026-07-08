import type { IndustryRoot } from "@/lib/api/search";

export interface FlatIndustry {
  id: string;
  level: number; // 0 | 1 | 2
  name_vi: string;
  name_en: string;
  /** Breadcrumb path in Vietnamese: "Root › Branch › Leaf" */
  pathVi: string;
  /** Breadcrumb path in English: "Root › Branch › Leaf" */
  pathEn: string;
  /** Normalized (lowercased, diacritics stripped) vi + en names + paths for substring matching. */
  search: string;
}

const SEP = " › ";

/**
 * Lowercases, strips Vietnamese diacritics, and collapses whitespace.
 * Used to build the `search` field and normalize query strings for matching.
 */
export function normalize(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * DFS traversal: root → branch → leaf.
 * Builds bilingual path strings and a normalized search field for each node.
 */
export function flattenIndustries(roots: IndustryRoot[]): FlatIndustry[] {
  const result: FlatIndustry[] = [];

  for (const root of roots) {
    const rootPathVi = root.name_vi;
    const rootPathEn = root.name_en;
    const rootSearch = normalize(`${root.name_vi} ${root.name_en} ${rootPathVi} ${rootPathEn}`);

    result.push({
      id: root.id,
      level: root.level,
      name_vi: root.name_vi,
      name_en: root.name_en,
      pathVi: rootPathVi,
      pathEn: rootPathEn,
      search: rootSearch,
    });

    for (const branch of root.children) {
      const branchPathVi = `${rootPathVi}${SEP}${branch.name_vi}`;
      const branchPathEn = `${rootPathEn}${SEP}${branch.name_en}`;
      const branchSearch = normalize(
        `${branch.name_vi} ${branch.name_en} ${branchPathVi} ${branchPathEn}`,
      );

      result.push({
        id: branch.id,
        level: branch.level,
        name_vi: branch.name_vi,
        name_en: branch.name_en,
        pathVi: branchPathVi,
        pathEn: branchPathEn,
        search: branchSearch,
      });

      for (const leaf of branch.children) {
        const leafPathVi = `${branchPathVi}${SEP}${leaf.name_vi}`;
        const leafPathEn = `${branchPathEn}${SEP}${leaf.name_en}`;
        const leafSearch = normalize(
          `${leaf.name_vi} ${leaf.name_en} ${leafPathVi} ${leafPathEn}`,
        );

        result.push({
          id: leaf.id,
          level: leaf.level,
          name_vi: leaf.name_vi,
          name_en: leaf.name_en,
          pathVi: leafPathVi,
          pathEn: leafPathEn,
          search: leafSearch,
        });
      }
    }
  }

  return result;
}

/** Return the flat node for the given id, or null. */
export function findIndustry(
  flat: FlatIndustry[],
  id: string | null | undefined,
): FlatIndustry | null {
  if (!id) return null;
  return flat.find((n) => n.id === id) ?? null;
}

const MAX_UNFILTERED = 200;

/**
 * Normalized substring/token match on the `search` field.
 * Empty query returns all nodes (capped at MAX_UNFILTERED).
 */
export function filterIndustries(flat: FlatIndustry[], query: string): FlatIndustry[] {
  if (!query.trim()) return flat.slice(0, MAX_UNFILTERED);

  const norm = normalize(query);
  const tokens = norm.split(" ").filter(Boolean);

  return flat.filter((node) => {
    // Prefer substring match on the full normalized search blob.
    if (node.search.includes(norm)) return true;
    // Fall back to all tokens being present somewhere (order-independent).
    return tokens.every((token) => node.search.includes(token));
  });
}

/**
 * Fuzzy name-based match for AI auto-select from a free-text industry name
 * extracted from a JD.
 *
 * Scoring:
 *   3 — exact normalized name match (vi or en)
 *   2 — all tokens of the query appear in the node's name (vi or en), normalized
 *   1 — substring match somewhere in the node's normalized search field
 *   0 — no match
 *
 * On ties, prefers deeper level (leaf=2 > branch=1 > root=0).
 * Returns null when no node scores > 0 or the query is blank/null.
 */
export function matchIndustryByName(
  name: string | null | undefined,
  flat: FlatIndustry[],
): FlatIndustry | null {
  if (!name?.trim()) return null;

  const normQuery = normalize(name);
  const tokens = normQuery.split(" ").filter(Boolean);
  if (tokens.length === 0) return null;

  let best: FlatIndustry | null = null;
  let bestScore = 0;

  for (const node of flat) {
    const normVi = normalize(node.name_vi);
    const normEn = normalize(node.name_en);

    let score = 0;

    if (normVi === normQuery || normEn === normQuery) {
      // Exact name match
      score = 3;
    } else if (
      tokens.every((t) => normVi.includes(t)) ||
      tokens.every((t) => normEn.includes(t))
    ) {
      // All tokens present in vi or en name
      score = 2;
    } else if (node.search.includes(normQuery) || tokens.every((t) => node.search.includes(t))) {
      // Substring/token match anywhere in the search blob
      score = 1;
    }

    if (score === 0) continue;

    // Prefer higher score; break ties by deeper level
    if (score > bestScore || (score === bestScore && best !== null && node.level > best.level)) {
      best = node;
      bestScore = score;
    }
  }

  return best;
}
