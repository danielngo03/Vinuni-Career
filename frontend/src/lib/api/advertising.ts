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
}

export interface UpdatePlacementBody {
  placement_type?: PlacementType;
  package_id?: string;
  start_at?: string;
  disclosure_confirmed?: boolean;
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

/* ========================================================================== */
/* Campaign allocation engine (spec §7.0, owner decision 2026-07-10)          */
/* -------------------------------------------------------------------------- */
/* The CAMPAIGN layer sits ALONGSIDE the target-based placement model above —  */
/* it never replaces it. A campaign carries a budget + pacing + COARSE         */
/* targeting and competes for a surface's finite sponsored slots through the   */
/* allocation engine. Only the `paid_sponsored` disclosure is paid + its       */
/* non-removable label is never a UI option.                                   */
/* ========================================================================== */

/** Campaign lifecycle (`ad_campaigns.status`). */
export type CampaignStatus =
  | "draft"
  | "pending_review"
  | "approved"
  | "active"
  | "paused"
  | "ended"
  | "rejected";

/** Advertiser goal. Drives the delivery-event the surface reports back. */
export type CampaignObjective =
  | "awareness"
  | "traffic"
  | "applications"
  | "event_registration";

/** Budget pacing — spread evenly across the window, or spend as fast as allowed. */
export type CampaignPacing = "even" | "asap";

/** A public surface that declares finite sponsored slots. */
export type AdSurface =
  | "discovery_feed"
  | "public_job_board"
  | "company_directory"
  | "homepage"
  | "events";

/** Privacy-safe delivery event the surface reports (never PII/GPS/raw IP). */
export type DeliveryEventType =
  | "impression"
  | "click"
  | "apply_start"
  | "register_intent";

export const CAMPAIGN_STATUSES: CampaignStatus[] = [
  "draft",
  "pending_review",
  "approved",
  "active",
  "paused",
  "ended",
  "rejected",
];

export const CAMPAIGN_OBJECTIVES: CampaignObjective[] = [
  "awareness",
  "traffic",
  "applications",
  "event_registration",
];

export const CAMPAIGN_PACINGS: CampaignPacing[] = ["even", "asap"];

export const AD_SURFACES: AdSurface[] = [
  "discovery_feed",
  "public_job_board",
  "company_directory",
  "homepage",
  "events",
];

/* Coarse, privacy-safe targeting vocabularies — MIRROR the backend allowlist
   (`domain/targeting.py`). These are the ONLY selectable targeting tokens; the
   builder offers a picker over them (never a free-text GPS/exact-location box).
   The server re-validates + rejects any forbidden/sensitive dimension. */
export const COARSE_LOCATIONS = [
  "hanoi",
  "ho_chi_minh",
  "da_nang",
  "hai_phong",
  "can_tho",
  "binh_duong",
  "dong_nai",
  "north",
  "central",
  "south",
  "vinuni_campus",
  "remote",
  "overseas",
  "other",
] as const;

export const COARSE_MAJORS = [
  "computer_science",
  "engineering",
  "business",
  "economics",
  "health_sciences",
  "medicine",
  "nursing",
  "arts_sciences",
  "humanities",
  "design",
  "law",
  "hospitality",
  "undecided",
  "other",
] as const;

export const COARSE_CAREERS = [
  "software_engineering",
  "data",
  "ai_ml",
  "product",
  "design",
  "finance",
  "banking",
  "accounting",
  "marketing",
  "sales",
  "operations",
  "consulting",
  "research",
  "healthcare",
  "hospitality",
  "education",
  "legal",
  "human_resources",
  "supply_chain",
  "other",
] as const;

export const COARSE_WORK_MODES = ["onsite", "remote", "hybrid"] as const;

export const COARSE_YEAR_COHORTS = [
  "freshman",
  "sophomore",
  "junior",
  "senior",
  "graduate",
  "alumni",
] as const;

/** The public banner fields (never storage keys / internal refs). */
export interface AdCampaignCreative {
  headline: string | null;
  body: string | null;
  image_ref: string | null;
  click_target: string | null;
  /** Server-resolved localized alt (prefers alt_en then alt_vi). */
  alt: string | null;
  alt_vi: string | null;
  alt_en: string | null;
}

/** Coarse targeting a campaign carries. Empty = BROAD (matches everyone). */
export interface CampaignTargeting {
  locations?: string[];
  majors?: string[];
  careers?: string[];
  work_modes?: string[];
  year_cohorts?: string[];
  device_classes?: string[];
}

/**
 * Honest delivery/pacing state (never a bid, never a raw model score). Lets the
 * partner + university see a truthfully under-/over-delivering campaign.
 */
export interface CampaignDelivery {
  impression_goal: number;
  impressions_today: number;
  daily_cap: number | null;
  budget_exhausted: boolean;
  paced_out: boolean;
  serving_eligible: boolean;
}

/**
 * A campaign projection (`campaign_presenters.campaign`). The partner surface
 * omits `payment_reference` / `created_by` / `approved_by` (admin-only spend
 * oversight); the admin queue (`admin: true`) includes them plus the moderation
 * SLA age/overdue fields. Decimal money is a formatted string ("1500000.00").
 */
export interface AdCampaign {
  id: string;
  org_id: string;
  name: string;
  objective: CampaignObjective | string;
  objective_label: string;
  surface: AdSurface | string;
  status: CampaignStatus;
  status_label: string;
  pacing: CampaignPacing | string;
  pacing_label: string;
  budget_amount: string | null;
  spent_amount: string | null;
  currency: string;
  start_at: string | null;
  end_at: string | null;
  targeting: CampaignTargeting;
  creative: AdCampaignCreative;
  target_type: AdTargetType | string | null;
  target_id: string | null;
  disclosure_class: DisclosureClass | string;
  disclosure: InventoryDisclosure;
  disclosure_confirmed: boolean;
  is_paid: boolean;
  moderation_note: string | null;
  delivery: CampaignDelivery;
  submitted_at: string | null;
  approved_at: string | null;
  activated_at: string | null;
  paused_at: string | null;
  ended_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  version: number;
  /* Admin-only spend oversight (present on /admin/advertising only). */
  payment_reference?: string | null;
  paid_at?: string | null;
  created_by?: string;
  approved_by?: string | null;
  moderation_reason_code?: ModerationReasonCode | string | null;
  moderation_reason_label?: string | null;
  /* Moderation-queue SLA fields (admin projection). */
  due_by?: string | null;
  age_hours?: number | null;
  is_overdue?: boolean;
}

/** Lifetime aggregate performance for one campaign (privacy-safe counts). */
export interface CampaignPerformance {
  impressions: number;
  clicks: number;
  apply_starts: number;
  register_intents: number;
  /** 0..1 ratios (clicks/impressions, apply_starts/impressions). */
  ctr: number;
  apply_start_rate: number;
  spend_amount: string;
  currency: string;
}

/** University spend/health roll-up returned alongside the admin campaign queue. */
export interface CampaignSpendSummary {
  active_count: number;
  pending_review_count: number;
  total_spend_amount: string;
  currency: string;
}

/** A finite sponsored slot on a surface (`GET /advertising/surfaces`). */
export interface AdSurfaceSlot {
  id: string;
  code: string;
  surface: AdSurface | string;
  name: string;
  capacity: number;
  max_sponsored_share: number;
  is_active: boolean;
}

/** A single filled sponsored position (public projection — creative + disclosure). */
export interface AllocationItem {
  campaign_id: string;
  slot_code: string;
  surface: string;
  position: number;
  inventory_class: string;
  /** Always "sponsored" for the paid allocation engine. */
  source: string;
  name: string;
  objective: string;
  creative: AdCampaignCreative;
  target_type: string | null;
  target_id: string | null;
  /** Mandatory, NON-REMOVABLE paid disclosure — never stripped. */
  disclosure: InventoryDisclosure;
  /** Coarse, non-PII reason this item was allocated here. */
  match_reason: Record<string, unknown>;
}

/** VinUni-curated fallback for an unfilled slot (labelled curated; never paid). */
export interface AllocationCuratedFallback {
  source?: string;
  disclosure?: InventoryDisclosure;
  creative?: AdCampaignCreative | Record<string, unknown>;
  [key: string]: unknown;
}

export interface AllocationSlot {
  slot_code: string;
  slot_name: string;
  capacity: number;
  max_sponsored_share: number;
  filled: number;
  items: AllocationItem[];
  fallback: AllocationCuratedFallback | null;
}

/** The public allocation read for one surface + coarse viewer segment. */
export interface SurfaceAllocation {
  surface: string;
  viewer_segment_key: string;
  viewer_segment: {
    locations: string[];
    majors: string[];
    careers: string[];
    work_modes: string[];
    year_cohorts: string[];
    device_classes: string[];
  };
  generated_at: string;
  /** Always "paid_sponsored" — organic/recommended come from a separate path. */
  inventory_class: string;
  slots: AllocationSlot[];
}

/** A live allocation-decision record (university oversight). */
export interface CampaignAllocationRecord {
  id: string;
  campaign_id: string;
  slot_code: string;
  surface: string;
  segment_key: string;
  position: number;
  match_reason: Record<string, unknown>;
  pacing_state: Record<string, unknown>;
  allocated_at: string | null;
  expires_at: string | null;
}

/* -------- Campaign write bodies -------- */

/** Creative fields the builder submits (server sets the resolved `alt`). */
export interface CampaignCreativeInput {
  headline?: string | null;
  body?: string | null;
  image_ref?: string | null;
  click_target?: string | null;
  alt_vi?: string | null;
  alt_en?: string | null;
}

export interface CampaignCreateBody {
  name: string;
  objective: CampaignObjective;
  surface: AdSurface;
  /** Decimal string or number; the server parses + freezes it. */
  budget_amount: string | number;
  pacing?: CampaignPacing;
  start_at: string;
  end_at: string;
  /** Coarse allowlisted targeting only; empty/omitted = broad (untargeted). */
  targeting?: CampaignTargeting | null;
  creative?: CampaignCreativeInput | null;
  target_type?: AdTargetType | null;
  target_id?: string | null;
  disclosure_confirmed?: boolean;
}

export interface CampaignUpdateBody {
  name?: string;
  objective?: CampaignObjective;
  surface?: AdSurface;
  budget_amount?: string | number;
  pacing?: CampaignPacing;
  start_at?: string;
  end_at?: string;
  targeting?: CampaignTargeting | null;
  creative?: CampaignCreativeInput | null;
  target_type?: AdTargetType | null;
  target_id?: string | null;
  disclosure_confirmed?: boolean;
  version?: number;
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

  /* ====================================================================== */
  /* Campaign allocation engine                                             */
  /* ====================================================================== */

  /* ------------------------- Partner campaigns -------------------------- */

  /** The caller org's campaigns (any status). Cursor-paginated. */
  listCampaigns(opts?: {
    cursor?: string | null;
    limit?: number;
    status?: string | null;
  }): Promise<ApiListEnvelope<AdCampaign>> {
    return api.list<AdCampaign>("/advertising/campaigns", {
      query: {
        cursor: opts?.cursor ?? undefined,
        limit: opts?.limit,
        status: opts?.status ?? undefined,
      },
    });
  },

  /** Owner-full campaign detail (cross-org / unknown → 404). */
  getCampaign(campaignId: string): Promise<AdCampaign> {
    return api.get<AdCampaign>(`/advertising/campaigns/${campaignId}`);
  },

  /**
   * Create a draft campaign. Coarse targeting is validated server-side — a
   * forbidden/sensitive (GPS/exact-location/…) dimension is rejected 422
   * (`details.field` names the bad key). Empty targeting = broad.
   */
  createCampaign(body: CampaignCreateBody): Promise<AdCampaign> {
    return api.post<AdCampaign>("/advertising/campaigns", body);
  },

  /** Edit a draft/rejected campaign (optimistic `version`). */
  updateCampaign(
    campaignId: string,
    body: CampaignUpdateBody,
  ): Promise<AdCampaign> {
    return api.patch<AdCampaign>(`/advertising/campaigns/${campaignId}`, body);
  },

  /** Soft-delete a draft/rejected campaign. */
  deleteCampaign(campaignId: string): Promise<{ status: string }> {
    return api.delete<{ status: string }>(
      `/advertising/campaigns/${campaignId}`,
    );
  },

  /**
   * Submit for university review. `disclosure_confirmed` MUST be true or the
   * server replies 422 (`details.reason === "disclosure_required"`).
   */
  submitCampaign(
    campaignId: string,
    body?: { disclosure_confirmed?: boolean; version?: number },
  ): Promise<AdCampaign> {
    return api.post<AdCampaign>(
      `/advertising/campaigns/${campaignId}/submit`,
      body ?? {},
    );
  },

  /** Pause my running campaign (active → paused). */
  pauseCampaign(campaignId: string, version?: number): Promise<AdCampaign> {
    return api.post<AdCampaign>(`/advertising/campaigns/${campaignId}/pause`, {
      version,
    });
  },

  /** Resume my paused campaign (paused → active). */
  resumeCampaign(campaignId: string, version?: number): Promise<AdCampaign> {
    return api.post<AdCampaign>(`/advertising/campaigns/${campaignId}/resume`, {
      version,
    });
  },

  /** End my campaign (approved/active/paused → ended; terminal). */
  endCampaign(campaignId: string, version?: number): Promise<AdCampaign> {
    return api.post<AdCampaign>(`/advertising/campaigns/${campaignId}/end`, {
      version,
    });
  },

  /** My campaign's lifetime aggregate performance (privacy-safe counts). */
  campaignPerformance(campaignId: string): Promise<CampaignPerformance> {
    return api.get<CampaignPerformance>(
      `/advertising/campaigns/${campaignId}/performance`,
    );
  },

  /* --------------------- Public: surfaces + serving --------------------- */

  /** The sponsored-slot inventory per surface (public; guest-allowed). */
  async listSurfaces(): Promise<{ slots: AdSurfaceSlot[]; surfaces: string[] }> {
    const res = await apiFetch<ApiEnvelope<AdSurfaceSlot[]>>(
      "/advertising/surfaces",
      { method: "GET", skipAuth: true },
    );
    const meta = (res.meta ?? {}) as { surfaces?: string[] };
    return { slots: res.data, surfaces: meta.surfaces ?? [] };
  },

  /**
   * The filled sponsored slots for a surface + coarse viewer segment (public;
   * guest-allowed). Coarse list params (`location`/`major`/`career`) are sent as
   * repeated query params. Organic/recommended inventory is NOT returned here.
   */
  getAllocation(params: {
    surface: string;
    locations?: string[];
    majors?: string[];
    careers?: string[];
    work_mode?: string;
    cohort?: string;
    device?: string;
    session_id?: string;
    locale?: string;
  }): Promise<SurfaceAllocation> {
    const qs = new URLSearchParams();
    qs.set("surface", params.surface);
    for (const l of params.locations ?? []) qs.append("location", l);
    for (const m of params.majors ?? []) qs.append("major", m);
    for (const c of params.careers ?? []) qs.append("career", c);
    if (params.work_mode) qs.set("work_mode", params.work_mode);
    if (params.cohort) qs.set("cohort", params.cohort);
    if (params.device) qs.set("device", params.device);
    if (params.session_id) qs.set("session_id", params.session_id);
    qs.set("locale", params.locale ?? "vi");
    return api.get<SurfaceAllocation>(
      `/advertising/allocations?${qs.toString()}`,
      { skipAuth: true },
    );
  },

  /**
   * Record a privacy-safe delivery event (impression/click/…). Public +
   * best-effort — carries NO PII/GPS/raw IP, only the coarse target. An
   * impression also spends against the campaign budget server-side.
   */
  recordDeliveryEvent(body: {
    campaign_id: string;
    slot_code: string;
    event_type: DeliveryEventType;
  }): Promise<{ status: string; event_type: string }> {
    return api.post<{ status: string; event_type: string }>(
      "/advertising/events",
      body,
      { skipAuth: true },
    );
  },

  /* ----------------------- University oversight ------------------------- */

  /**
   * The campaign review queue + spend roll-up (`meta.spend` / `meta.count`).
   * University moderators only (permission → 403).
   */
  async listCampaignQueue(opts?: {
    status?: string | null;
    org_id?: string | null;
    limit?: number;
  }): Promise<{
    items: AdCampaign[];
    spend: CampaignSpendSummary | null;
    count: number;
  }> {
    const res = await apiFetch<ApiEnvelope<AdCampaign[]>>(
      "/admin/advertising/campaigns",
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
      spend?: CampaignSpendSummary;
      count?: number;
    };
    return {
      items: res.data,
      spend: meta.spend ?? null,
      count: typeof meta.count === "number" ? meta.count : res.data.length,
    };
  },

  /** Approve a campaign (disclosure + spend oversight OK). */
  approveCampaign(
    campaignId: string,
    opts?: { note?: string; version?: number },
  ): Promise<AdCampaign> {
    return api.post<AdCampaign>(
      `/admin/advertising/campaigns/${campaignId}/approve`,
      { note: opts?.note, version: opts?.version },
    );
  },

  /** Reject a campaign with a required reason. */
  rejectCampaign(
    campaignId: string,
    reason: string,
    version?: number,
    reasonCode?: ModerationReasonCode | string,
  ): Promise<AdCampaign> {
    return api.post<AdCampaign>(
      `/admin/advertising/campaigns/${campaignId}/reject`,
      { reason, reason_code: reasonCode, version },
    );
  },

  /** Record a manual/bank-transfer payment (spend oversight). */
  markCampaignPaid(
    campaignId: string,
    paymentReference: string,
    version?: number,
  ): Promise<AdCampaign> {
    return api.post<AdCampaign>(
      `/admin/advertising/campaigns/${campaignId}/mark-paid`,
      { payment_reference: paymentReference, version },
    );
  },

  /** Pause any campaign (university override). Reason optional. */
  adminPauseCampaign(
    campaignId: string,
    opts?: { reason?: string; version?: number },
  ): Promise<AdCampaign> {
    return api.post<AdCampaign>(
      `/admin/advertising/campaigns/${campaignId}/pause`,
      { reason: opts?.reason, version: opts?.version },
    );
  },

  /** Disable any campaign immediately (flags OFF). Reason optional. */
  disableCampaign(
    campaignId: string,
    opts?: { reason?: string; version?: number },
  ): Promise<AdCampaign> {
    return api.post<AdCampaign>(
      `/admin/advertising/campaigns/${campaignId}/disable`,
      { reason: opts?.reason, version: opts?.version },
    );
  },

  /**
   * Relabel a campaign's public inventory class. PAID inventory can never be
   * relabelled to a non-paid class — the server replies 409
   * (`details.reason === "paid_disclosure_immutable"`).
   */
  setCampaignDisclosureClass(
    campaignId: string,
    opts: { disclosure_class: DisclosureClass; version?: number },
  ): Promise<AdCampaign> {
    return api.post<AdCampaign>(
      `/admin/advertising/campaigns/${campaignId}/disclosure-class`,
      { disclosure_class: opts.disclosure_class, version: opts.version },
    );
  },

  /** Recent live allocation-decision records (university oversight). */
  async listCampaignAllocations(opts?: {
    surface?: string | null;
    limit?: number;
  }): Promise<CampaignAllocationRecord[]> {
    const res = await apiFetch<ApiEnvelope<CampaignAllocationRecord[]>>(
      "/admin/advertising/allocations",
      {
        method: "GET",
        query: {
          surface: opts?.surface ?? undefined,
          limit: opts?.limit,
        },
      },
    );
    return res.data;
  },
};
