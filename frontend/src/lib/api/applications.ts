/**
 * Barrel for the applications domain. The actual implementation is split into
 * `applications/{core,scorecards,interviews,offers}.ts` — one file per
 * ADR-owned sub-domain (pipeline/reveal, ADR-0005 scorecards, ADR-0006
 * interviews, ADR-0007 offers) — instead of one 1000+ line module, so each
 * area can be reviewed and changed independently. This file's import path
 * (`@/lib/api/applications`) and the merged `applicationsApi` object are kept
 * stable so no call site needs to change.
 */
import { applicationsCoreApi } from "./applications/core";
import { scorecardsApi } from "./applications/scorecards";
import { interviewsApi } from "./applications/interviews";
import { offersApi } from "./applications/offers";

export * from "./applications/core";
export * from "./applications/scorecards";
export * from "./applications/interviews";
export * from "./applications/offers";

export const applicationsApi = {
  ...applicationsCoreApi,
  ...scorecardsApi,
  ...interviewsApi,
  ...offersApi,
};
