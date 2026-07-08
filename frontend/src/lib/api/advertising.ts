import { api, apiFetch, apiUpload } from "./client";
import type { ApiEnvelope, ApiListEnvelope } from "./types";
import type { DisclosureClass, InventoryDisclosure } from "./discovery";
import type {
  BulkModerationResultItem,
  ModerationReasonCode,
} from "./jobs";

/* ------------------------------- Vocabularies ----------------------------- */

/**
 * Placement lifecycle (ADR-0009 §3). A partner request to sponsor/feature one of
 * their own jobs/events, university-approved + manually paid, inside a date
 * window. The non-removable sponsored/featured label is driven by activation —
 * it is never a UI option.
 */
export type PlacementStatus =
  | "draft"
  | "pending_approval"
  | "approved"
  | "active"
  | "completed"
  | "rejected"
  | "cancelled";

/** What the placement grants. A package constrains the selectable type. */
export type PlacementType = "sponsored" | "featured" | "both";

/** The polymorphic target — one of the partner's OWN jobs or events. */
export type AdTargetType = "job" | "event";

export const PLACEMENT_STATUSES: PlacementStatus[] = [
  "draft",
  "pending_approval",
  "approved",
  "active",
  "completed",
  "rejected",
  "cancelled",
];

/* ------------------------------- Targeting -------------------------------- */

/**
 * Audience-targeting mode for a sponsored placement (spec §4/§7).
 * `automatic` = broad reach (no dimensions). `manual` = partner-declared
 * allowlisted values. `university_restricted` = the university set the audience
 * and the partner may NOT edit it (the partner write path 422s
 * `restricted_by_university`).
 */
export type TargetingMode = "automatic" | "manual" | "university_restricted";

/**
 * The SIX allowlisted, privacy-safe targeting dimensions. NEVER any PII /
 * sensitive category — the backend rejects a forbidden dimension outright.
 */
export type TargetingDimension =
  | "region"
  | "industry"
  | "role_family"
  | "work_mode"
  | "student_segment"
  | "language";

export const TARGETING_DIMENSIONS: TargetingDimension[] = [
  "region",
  "industry",
  "role_family",
  "work_mode",
  "student_segment",
  "language",
];

/**
 * A validated, allowlist-safe audience descriptor persisted on a placement. The
 * backend re-normalizes on read, so this only ever carries the six coarse
 * dimensions — never a forbidden/PII signal.
 */
export interface TargetingDescriptor {
  mode: TargetingMode | string;
  dimensions: Partial<Record<TargetingDimension, string[]>>;
}

/* --------------------------- Creative policy flags ------------------------ */

/** Deterministic creative pre-check codes (advisory; a human still approves). */
export type CreativePolicyCode =
  | "creative_dimension_mismatch"
  | "creative_low_resolution"
  | "banned_claim"
  | "off_platform_contact"
  | "disclosure_impersonation";

export type CreativePolicySeverity = "high" | "medium" | "low";

/**
 * One advisory pre-flag returned on the creative UPLOAD response only (spec
 * §5/§9). The creative stays `pending` for human review; a flag never
 * auto-rejects. `detail` is user-safe (no internals).
 */
export interface CreativePolicyFlag {
  code: CreativePolicyCode | string;
  severity: CreativePolicySeverity | string;
  detail: string;
}

/* ------------------------------- Creatives -------------------------------- */

/**
 * A campaign-creative delivery slot (spec §5). V1 serves the two PRIMARY public
 * slots publicly (hero + right rail); the inline-card / event-banner slots accept
 * staged uploads but are not wired to a public read yet.
 */
export type CreativeSlot =
  | "homepage_hero"
  | "right_rail"
  | "inline_card"
  | "event_banner";

/** Creative review state — independent of the placement lifecycle. */
export type CreativeModerationStatus = "pending" | "approved" | "rejected";

/** University approve/reject decision for an uploaded creative. */
export type CreativeDecision = "approve" | "reject";

export const CREATIVE_SLOTS: CreativeSlot[] = [
  "homepage_hero",
  "right_rail",
  "inline_card",
  "event_banner",
];

/**
 * The two public-served slots — a placement needs an APPROVED creative in these
 * before it can run (drives `missing_primary_slots` / the "asset required" state).
 */
export const PRIMARY_CREATIVE_SLOTS: CreativeSlot[] = [
  "homepage_hero",
  "right_rail",
];

/** Desktop/mobile asset guidance for a slot (spec §5 table). */
export interface CreativeAssetRequirements {
  desktop?: string;
  desktop_ratio?: string;
  mobile?: string;
  mobile_ratio?: string;
  use?: string;
}

/**
 * Client mirror of the backend `SLOT_SPECS` (`domain/creatives.py`). Used for the
 * upload size/aspect HINT and the responsive desktop/mobile preview frames before
 * a creative exists. The server remains the source of truth on validation.
 */
export const CREATIVE_SLOT_SPECS: Record<CreativeSlot, CreativeAssetRequirements> = {
  homepage_hero: {
    desktop: "1440x360",
    desktop_ratio: "4:1",
    mobile: "720x720",
    mobile_ratio: "1:1",
    use: "top campaign carousel",
  },
  right_rail: {
    desktop: "640x800",
    desktop_ratio: "4:5",
    mobile: "720x720",
    mobile_ratio: "1:1",
    use: "homepage / job detail rail",
  },
  inline_card: {
    desktop: "1200x630",
    desktop_ratio: "1.91:1",
    mobile: "720x900",
    mobile_ratio: "4:5",
    use: "between job/event rails",
  },
  event_banner: {
    desktop: "1440x480",
    desktop_ratio: "3:1",
    mobile: "720x900",
    mobile_ratio: "4:5",
    use: "events / career explore",
  },
};

/** Aspect-ratio CSS value (`w / h`) parsed from a slot's `*_ratio` (for preview frames). */
export function ratioToCss(ratio: string | undefined): string | undefined {
  if (!ratio) return undefined;
  const [w, h] = ratio.split(":").map((n) => Number.parseFloat(n));
  if (!w || !h) return undefined;
  return `${w} / ${h}`;
}

/**
 * An uploaded campaign creative (owner / admin projection from `presenters.creative`).
 * `image_url` is the public serve route (re-checks approval + active placement on
 * every request) — never a raw storage key. A freshly uploaded or replaced creative
 * is always `pending` until the university reviews it.
 */
export interface PlacementCreative {
  id: string;
  placement_id: string;
  slot: CreativeSlot | string;
  slot_label: string;
  asset_requirements: CreativeAssetRequirements;
  image_url: string;
  media_type: string | null;
  alt: string | null;
  alt_vi: string | null;
  alt_en: string | null;
  focal_point: { x: number; y: number };
  click_target: string | null;
  moderation_status: CreativeModerationStatus | string;
  moderation_status_label: string;
  moderation_note: string | null;
  start_at: string | null;
  end_at: string | null;
  analytics_source_surface: string | null;
  created_at: string | null;
  updated_at: string | null;
  version: number;
  /**
   * Advisory policy pre-flags — present ONLY on the upload response (spec §5/§9),
   * never on the list/detail projection. The creative stays `pending` regardless.
   */
  policy_flags?: CreativePolicyFlag[];
}

/* ------------------------------- Wire types ------------------------------- */

/**
 * A pricing tier (`GET /advertising/packages`). `price_amount` is a decimal
 * string (e.g. "1500000.00"); render via `formatVnd`. `grants_*` constrain which
 * `placement_type` the package can request.
 */
export interface AdPackage {
  id: string;
  code: string;
  name: string;
  placement_type: PlacementType;
  placement_type_label: string;
  price_amount: string | null;
  currency: string;
  duration_days: number;
  grants_sponsored: boolean;
  grants_featured: boolean;
  is_active: boolean;
}

/**
 * A placement projection. The partner surface omits `payment_reference` /
 * `created_by` / `approved_by` (admin-only spend oversight); the admin surface
 * (`admin: true`) includes them. `target_title` may be null if the underlying
 * job/event is no longer loadable. Decimal `price_amount` is the frozen snapshot.
 */
export interface Placement {
  id: string;
  org_id: string;
  target_type: AdTargetType;
  target_type_label: string;
  target_id: string;
  target_title: string | null;
  placement_type: PlacementType;
  placement_type_label: string;
  package_id: string;
  package: AdPackage | null;
  price_amount: string | null;
  currency: string;
  start_at: string | null;
  end_at: string | null;
  status: PlacementStatus;
  status_label: string;
  disclosure_confirmed: boolean;
  moderation_note: string | null;
  moderation_reason_code?: ModerationReasonCode | string | null;
  moderation_reason_label?: string | null;
  /** Moderation queue assignment (claim/SLA — university moderation only). */
  claimed_by?: string | null;
  claimed_at?: string | null;
  due_by?: string | null;
  age_hours?: number | null;
  is_overdue?: boolean;
  is_paid: boolean;
  paid_at: string | null;
  submitted_at: string | null;
  approved_at: string | null;
  activated_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  version: number;
  /* Campaign disclosure + creatives (spec §4/§5/§6). The public inventory class
     and its polished, class-keyed disclosure descriptor — only `paid_sponsored`
     is paid + non-removable. `creatives` is the placement's uploaded banners;
     `missing_primary_slots` lists primary slots still lacking an APPROVED
     creative ("asset required before this can run"). */
  disclosure_class?: DisclosureClass | string;
  disclosure?: InventoryDisclosure;
  /** Audience-targeting descriptor (allowlist-safe; never PII). Always present. */
  targeting?: TargetingDescriptor;
  creatives?: PlacementCreative[];
  missing_primary_slots?: (CreativeSlot | string)[];
  has_approved_creative?: boolean;
  /* Admin-only spend-oversight fields (present on /admin/advertising only). */
  payment_reference?: string | null;
  created_by?: string;
  approved_by?: string | null;
}

/** University spend roll-up returned alongside the admin placement list. */
export interface AdvertisingSpend {
  active_count: number;
  pending_approval_count: number;
  active_spend_amount: string;
  currency: string;
}

/* ------------------------------- Analytics -------------------------------- */

/**
 * Aggregate campaign counters (spec §7). Privacy-safe totals ONLY — never an
 * individual viewer, session, or candidate id, and never PII.
 */
export interface AdAnalyticsCounters {
  impressions: number;
  clicks: number;
  views: number;
  apply_starts: number;
  save_intents: number;
  event_register_intents: number;
}

/** One day of a placement's aggregate metrics. */
export interface PlacementAnalyticsDay extends AdAnalyticsCounters {
  date: string;
  ctr_pct: number | null;
}

/**
 * Per-campaign analytics (`GET /advertising/placements/{id}/analytics`).
 * Owner-scoped: a cross-org / unknown placement is a non-enumerable 404.
 */
export interface PlacementAnalytics {
  placement_id: string;
  org_id: string;
  totals: AdAnalyticsCounters;
  ctr_pct: number | null;
  apply_start_rate_pct: number | null;
  /** Decimal string — the partner's OWN frozen campaign price / apply-starts. */
  cost_per_apply_start: string | null;
  campaign_price: string | null;
  currency: string;
  daily: PlacementAnalyticsDay[];
  day_count: number;
  /** Backend-localized aggregates-only disclaimer. */
  note: string;
}

/** One campaign row inside the org rollup. */
export interface OrgAnalyticsCampaign extends AdAnalyticsCounters {
  placement_id: string;
  ctr_pct: number | null;
}

/** Org-wide campaign rollup (`GET /advertising/analytics`). */
export interface OrgAnalytics {
  org_id: string;
  campaign_count: number;
  totals: AdAnalyticsCounters;
  ctr_pct: number | null;
  apply_start_rate_pct: number | null;
  campaigns: OrgAnalyticsCampaign[];
  note: string;
}

/* ------------------------------- Write bodies ----------------------------- */

export interface CreatePlacementBody {
  target_type: AdTargetType;
  target_id: string;
  placement_type: PlacementType;
  package_id: string;
  /** ISO datetime — start of the date window; `end_at` is derived from duration. */
  start_at: string;
  /** Acknowledges the non-removable label; required true before submit. */
  disclosure_confirmed?: boolean;
  /** Optional audience descriptor. Omit for broad reach (server defaults it). */
  targeting?: TargetingDescriptor;
}

export interface UpdatePlacementBody {
  placement_type?: PlacementType;
  package_id?: string;
  start_at?: string;
  disclosure_confirmed?: boolean;
  /**
   * Audience descriptor. NEVER send for a `university_restricted` placement —
   * the server 422s `restricted_by_university`.
   */
  targeting?: TargetingDescriptor;
  version?: number;
}

/** Multipart creative upload (spec §5). The browser sets the boundary. */
export interface UploadCreativeBody {
  file: File;
  slot: CreativeSlot;
  alt_vi?: string;
  alt_en?: string;
  /** Focal point 0..1 for responsive crop (`object-position`). */
  focal_x: number;
  focal_y: number;
  click_target?: string;
}

/* --------------------------------- Calls ---------------------------------- */

export const advertisingApi = {
  /* ------------------------------ Partner ------------------------------- */

  /** Pricing tiers (name + placement type + price + duration). */
  listPackages(): Promise<AdPackage[]> {
    return api.get<AdPackage[]>("/advertising/packages");
  },

  /** The caller org's placements (any status). Cursor-paginated. */
  listPlacements(opts?: {
    cursor?: string | null;
    limit?: number;
    status?: string | null;
  }): Promise<ApiListEnvelope<Placement>> {
    return api.list<Placement>("/advertising/placements", {
      query: {
        cursor: opts?.cursor ?? undefined,
        limit: opts?.limit,
        status: opts?.status ?? undefined,
      },
    });
  },

  /** Owner-full placement detail (cross-org / unknown → 404). */
  getPlacement(placementId: string): Promise<Placement> {
    return api.get<Placement>(`/advertising/placements/${placementId}`);
  },

  /**
   * Owner-scoped per-campaign analytics (spec §7). Aggregates only — never an
   * individual viewer/PII. A cross-org / unknown placement is a non-enumerable
   * 404 (render a not-authorized/empty state).
   */
  getPlacementAnalytics(placementId: string): Promise<PlacementAnalytics> {
    return api.get<PlacementAnalytics>(
      `/advertising/placements/${placementId}/analytics`,
    );
  },

  /** The caller org's campaign analytics rollup (aggregates only). */
  getOrgAnalytics(): Promise<OrgAnalytics> {
    return api.get<OrgAnalytics>("/advertising/analytics");
  },

  /**
   * Create a draft placement. Validates target ownership server-side
   * (cross-org/unknown target → 404). The label is applied on activation; there
   * is no field to suppress it.
   */
  createPlacement(body: CreatePlacementBody): Promise<Placement> {
    return api.post<Placement>("/advertising/placements", body);
  },

  /** Edit a draft/rejected placement (optimistic `version`). */
  updatePlacement(
    placementId: string,
    body: UpdatePlacementBody,
  ): Promise<Placement> {
    return api.patch<Placement>(`/advertising/placements/${placementId}`, body);
  },

  /** Soft-delete a draft/rejected placement. */
  deletePlacement(placementId: string): Promise<{ status: string }> {
    return api.delete<{ status: string }>(
      `/advertising/placements/${placementId}`,
    );
  },

  /* ----------------------------- Creatives ------------------------------ */

  /** The caller placement's uploaded creatives (owner-scoped; cross-org → 404). */
  listCreatives(placementId: string): Promise<PlacementCreative[]> {
    return api.get<PlacementCreative[]>(
      `/advertising/placements/${placementId}/creatives`,
    );
  },

  /**
   * Upload a banner creative for a slot (multipart). 422 carries
   * `details.reason` (`file_too_large` / `unsupported_image_type` / `empty_file`)
   * or `details.field` (`slot` / `focal_x` / `focal_y`). A fresh creative is
   * always `pending` review. 404 if the placement is not the caller's.
   */
  uploadCreative(
    placementId: string,
    body: UploadCreativeBody,
  ): Promise<PlacementCreative> {
    const form = new FormData();
    form.append("file", body.file);
    form.append("slot", body.slot);
    if (body.alt_vi) form.append("alt_vi", body.alt_vi);
    if (body.alt_en) form.append("alt_en", body.alt_en);
    form.append("focal_x", String(body.focal_x));
    form.append("focal_y", String(body.focal_y));
    if (body.click_target) form.append("click_target", body.click_target);
    return apiUpload<ApiEnvelope<PlacementCreative>>(
      `/advertising/placements/${placementId}/creatives`,
      form,
    ).then((res) => res.data);
  },

  /** Soft-delete a creative (owner-scoped; cross-org → 404). */
  deleteCreative(creativeId: string): Promise<{ status: string }> {
    return api.delete<{ status: string }>(
      `/advertising/creatives/${creativeId}`,
    );
  },

  /**
   * Submit for university approval. `disclosure_confirmed` MUST be true or the
   * server replies 422 (`details.reason === "disclosure_required"`). 409 on
   * `active_placement_limit` / `placement_exists` / `version_conflict`.
   */
  submitPlacement(
    placementId: string,
    body?: { disclosure_confirmed?: boolean; version?: number },
  ): Promise<Placement> {
    return api.post<Placement>(
      `/advertising/placements/${placementId}/submit`,
      body ?? {},
    );
  },

  /** Cancel the caller's own placement (pre-completed) → cancelled, flags OFF. */
  cancelPlacement(placementId: string, version?: number): Promise<Placement> {
    return api.post<Placement>(`/advertising/placements/${placementId}/cancel`, {
      version,
    });
  },

  /* --------------------------- University admin ------------------------- */

  /**
   * ALL placements + the spend roll-up (`meta.spend`). University moderators
   * only (permission → 403). Returns the raw envelope so callers can read
   * `meta.spend` and `meta.count`.
   */
  async listAllPlacements(opts?: {
    status?: string | null;
    org_id?: string | null;
    limit?: number;
  }): Promise<{ items: Placement[]; spend: AdvertisingSpend | null; count: number }> {
    const res = await apiFetch<ApiEnvelope<Placement[]>>(
      "/admin/advertising/placements",
      {
        method: "GET",
        query: {
          status: opts?.status ?? undefined,
          org_id: opts?.org_id ?? undefined,
          limit: opts?.limit,
        },
      },
    );
    const meta = (res.meta ?? {}) as {
      spend?: AdvertisingSpend;
      count?: number;
    };
    return {
      items: res.data,
      spend: meta.spend ?? null,
      count: typeof meta.count === "number" ? meta.count : res.data.length,
    };
  },

  /** Approve (disclosure + spend OK). pending_approval → approved. */
  approvePlacement(
    placementId: string,
    opts?: { note?: string; version?: number },
  ): Promise<Placement> {
    return api.post<Placement>(
      `/admin/advertising/placements/${placementId}/approve`,
      { note: opts?.note, version: opts?.version },
    );
  },

  /** Reject with a required coded reason. pending_approval → rejected. */
  rejectPlacement(
    placementId: string,
    reason: string,
    version?: number,
    reasonCode?: ModerationReasonCode | string,
  ): Promise<Placement> {
    return api.post<Placement>(
      `/admin/advertising/placements/${placementId}/reject`,
      { reason, reason_code: reasonCode, version },
    );
  },

  /** Claim a pending placement for review (concurrency-safe; 409 if already claimed). */
  claimPlacement(placementId: string): Promise<Placement> {
    return api.post<Placement>(
      `/admin/advertising/placements/${placementId}/claim`,
    );
  },

  /** Escalate a placement to the shared human review queue. */
  escalatePlacement(
    placementId: string,
    opts?: { reason_code?: ModerationReasonCode | string; note?: string },
  ): Promise<Placement> {
    return api.post<Placement>(
      `/admin/advertising/placements/${placementId}/escalate`,
      opts ?? {},
    );
  },

  /** Approve multiple placements; each item succeeds/fails independently. */
  bulkApprovePlacements(
    placementIds: string[],
  ): Promise<BulkModerationResultItem[]> {
    return api.post<BulkModerationResultItem[]>(
      "/admin/advertising/placements/bulk-approve",
      { placement_ids: placementIds },
    );
  },

  /** Reject multiple placements; each item succeeds/fails independently. */
  bulkRejectPlacements(
    items: { id: string; reason: string; reason_code?: ModerationReasonCode | string }[],
  ): Promise<BulkModerationResultItem[]> {
    return api.post<BulkModerationResultItem[]>(
      "/admin/advertising/placements/bulk-reject",
      { items },
    );
  },

  /** Record a manual/bank-transfer payment (sets paid_at + reference). */
  markPaid(
    placementId: string,
    paymentReference: string,
    version?: number,
  ): Promise<Placement> {
    return api.post<Placement>(
      `/admin/advertising/placements/${placementId}/mark-paid`,
      { payment_reference: paymentReference, version },
    );
  },

  /** Disable any placement immediately (flags OFF). Reason optional. */
  disablePlacement(
    placementId: string,
    opts?: { reason?: string; version?: number },
  ): Promise<Placement> {
    return api.post<Placement>(
      `/admin/advertising/placements/${placementId}/cancel`,
      { reason: opts?.reason, version: opts?.version },
    );
  },

  /**
   * Approve or reject an uploaded creative (spec §6). A `reject` requires a
   * `note` (server replies 422 `details.reason === "reason_required"` otherwise).
   * Only an approved creative on an active placement is ever served publicly.
   */
  reviewCreative(
    creativeId: string,
    opts: { decision: CreativeDecision; note?: string; version?: number },
  ): Promise<PlacementCreative> {
    return api.post<PlacementCreative>(
      `/admin/advertising/creatives/${creativeId}/review`,
      { decision: opts.decision, note: opts.note, version: opts.version },
    );
  },

  /**
   * Relabel a placement's public inventory class (spec §4). PAID inventory can
   * never be relabelled to a non-paid editorial/partnership class — the server
   * replies 409 `details.reason === "paid_disclosure_immutable"`.
   */
  setDisclosureClass(
    placementId: string,
    opts: { disclosure_class: DisclosureClass; version?: number },
  ): Promise<Placement> {
    return api.post<Placement>(
      `/admin/advertising/placements/${placementId}/disclosure-class`,
      { disclosure_class: opts.disclosure_class, version: opts.version },
    );
  },
};
