"use client";

import { useState, useMemo } from "react";
import {
  useForm,
  Controller,
  type UseFormRegisterReturn,
  type UseFormRegister,
  type FieldErrors,
} from "react-hook-form";
import { useTranslations } from "next-intl";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  FloppyDisk,
  Eye,
} from "@phosphor-icons/react";
import { JobLocationPicker } from "./location-picker";
import { IndustryPicker } from "@/components/jobs/industry-picker";
import type { JobLocationItem, CandidateRequirements } from "@/lib/api/jobs";
import {
  Button,
  Input,
  Textarea,
  Select,
  Modal,
  useToast,
  SegmentedControl,
} from "@/components/ui";
import { JobPreview } from "./job-preview";
import {
  RequirementGroupField,
  AgeRequirementField,
  LanguageRows,
  CertificationRows,
} from "@/components/jobs/eligibility";
import { FieldProvenance, useProvenance } from "@/components/jobs/field-provenance";
import { zodResolver } from "@/lib/validation/resolver";
import {
  jobFormSchema,
  JOB_FORM_DEFAULTS,
  EMPTY_CANDIDATE_REQUIREMENTS,
  type JobFormValues,
} from "@/lib/validation/jobs";
import { useApiErrorMessage, applyFieldErrors } from "@/lib/auth/use-api-error";
import { parseTags } from "@/lib/jobs/format";
import {
  ApiError,
  jobsApi,
  EMPLOYMENT_TYPES,
  JOB_VISIBILITIES,
  type JobCreateBody,
  type JobQualityIssue,
  type OwnerJobDetail,
} from "@/lib/api";
import { JdWriterButton } from "./jd-writer-button";
import { JdUploadButton } from "./jd-upload-button";
import { JdFieldIssueNote } from "./jd-quality-panel";
import type { JdUploadResult } from "@/lib/api/jobs";
import { isRemoderationField } from "@/lib/jobs/amendment";
import { flattenIndustries, matchIndustryByName } from "@/lib/jobs/industry-lookup";
import { searchApi } from "@/lib/api/search";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/layout/page-header";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Friendly label for a re-moderation field shown in the amendment confirm
 * modal. Falls back to the raw field key for any future backend field this
 * list hasn't caught up with yet.
 */
function amendmentFieldName(tf: (key: string) => string, field: string): string {
  const known = new Set([
    "title",
    "description",
    "requirements",
    "employment_type",
    "location_type",
    "location_city",
    "location_country",
    "locations",
    "required_skills",
    "preferred_skills",
    "experience_min_years",
    "experience_max_years",
    "degree_required",
    "salary_is_disclosed",
    "salary_min",
    "salary_max",
    "salary_currency",
    // Structured salary/experience/eligibility fields (F2)
    "salary_mode",
    "salary_period",
    "salary_gross_net",
    "experience_mode",
    "seniority_level",
    "candidate_requirements",
    "industry_id",
  ]);
  return known.has(field) ? tf(`amendment.fieldNames.${field}`) : field;
}

/**
 * Prune a CandidateRequirements object before sending to the API.
 * Drops groups with mode "not_required" and empty values; drops empty
 * languages/certifications arrays; drops null/empty note.
 * Returns undefined when the whole block is empty (nothing to send).
 */
function pruneCandidateRequirements(
  cr: CandidateRequirements,
): CandidateRequirements | undefined {
  const pruned: CandidateRequirements = {};

  const groups = [
    "education",
    "nationalities",
    "gender",
    "marital_status",
  ] as const;
  for (const key of groups) {
    const g = cr[key];
    if (g && !(g.mode === "not_required" && g.values.length === 0)) {
      pruned[key] = g;
    }
  }

  // Age: keep only when mode is not "not_required"
  if (cr.age && cr.age.mode !== "not_required") {
    pruned.age = cr.age;
  }

  // Languages: keep only non-empty rows
  const langs = (cr.languages ?? []).filter((l) => l.language.trim() !== "");
  if (langs.length > 0) pruned.languages = langs;

  // Certifications: keep only non-empty rows
  const certs = (cr.certifications ?? []).filter((c) => c.name.trim() !== "");
  if (certs.length > 0) pruned.certifications = certs;

  // Note: keep only non-empty
  const note = cr.note?.trim() ?? "";
  if (note) pruned.note = note;

  // If nothing remains, return undefined (omit the field from the body)
  if (Object.keys(pruned).length === 0) return undefined;
  return pruned;
}

/**
 * Derive salary_min/salary_max per salary_mode.
 * negotiable/hidden: null/null
 * from: min/null
 * to: null/max
 * fixed: min/min (same amount)
 * range: min/max as entered
 */
function deriveSalaryMinMax(
  mode: JobFormValues["salary_mode"],
  rawMin: string,
  rawMax: string,
): { salary_min: number | null; salary_max: number | null } {
  const min = rawMin ? Number(rawMin) : null;
  const max = rawMax ? Number(rawMax) : null;
  switch (mode) {
    case "negotiable":
      return { salary_min: null, salary_max: null };
    case "hidden":
      return { salary_min: min, salary_max: max };
    case "from":
      return { salary_min: min, salary_max: null };
    case "to":
      return { salary_min: null, salary_max: max };
    case "fixed":
      return { salary_min: min, salary_max: min };
    case "range":
      return { salary_min: min, salary_max: max };
    default:
      return { salary_min: min, salary_max: max };
  }
}

/** Concrete language codes the backend can store for a JD's original language. */
const STORABLE_LANGUAGE_CODES = ["vi", "en", "ja", "ko", "zh"] as const;
type StorableLanguageCode = (typeof STORABLE_LANGUAGE_CODES)[number];

/**
 * Normalize a raw language value (from JD-upload `detected_language` or a
 * stored `job.language_code`) into a concrete, storable form value.
 * - "mixed" (bilingual JD) -> "vi" (the local default)
 * - "unknown" / empty / any non-storable value -> undefined (let the backend
 *   auto-detect; the form shows the "Auto-detect" option)
 */
function normalizeLanguageCode(
  raw: string | null | undefined,
): StorableLanguageCode | undefined {
  if (!raw) return undefined;
  if (raw === "mixed") return "vi";
  return (STORABLE_LANGUAGE_CODES as readonly string[]).includes(raw)
    ? (raw as StorableLanguageCode)
    : undefined;
}

/**
 * Map `JobFormValues` + external state to a `JobCreateBody` ready for the API.
 * `cv_language_required` is forwarded as-is; "any" is the server default.
 */
function toBody(
  v: JobFormValues,
  locations: JobLocationItem[],
  candidateRequirements: CandidateRequirements,
): JobCreateBody {
  const salaryMode = v.salary_mode;
  const salaryIsDisclosed = !(salaryMode === "negotiable" || salaryMode === "hidden");
  const { salary_min, salary_max } = deriveSalaryMinMax(
    salaryMode,
    v.salary_min ?? "",
    v.salary_max ?? "",
  );

  // Use multi-location array; set legacy fields from first item for backend compat.
  const primaryLoc = locations[0];
  const body: JobCreateBody = {
    title: v.title.trim(),
    description: v.description.trim(),
    requirements: v.requirements?.trim() || null,
    benefits: v.benefits?.trim() || null,
    employment_type: v.employment_type,
    location_type: primaryLoc?.type ?? v.location_type,
    location_city: primaryLoc?.city || v.location_city?.trim() || null,
    location_country: primaryLoc?.country || v.location_country.trim() || "Vietnam",
    locations: locations.length > 0 ? locations : undefined,
    required_skills: parseTags(v.required_skills),
    preferred_skills: parseTags(v.preferred_skills),
    experience_min_years: v.experience_min_years ? Number(v.experience_min_years) : null,
    experience_max_years: v.experience_max_years ? Number(v.experience_max_years) : null,
    degree_required: v.degree_required?.trim() || null,
    salary_is_disclosed: salaryIsDisclosed,
    salary_min,
    salary_max,
    salary_currency: v.salary_currency.trim() || "VND",
    salary_mode: salaryMode,
    salary_period: v.salary_period,
    salary_gross_net: v.salary_gross_net,
    experience_mode: v.experience_mode,
    seniority_level: v.seniority_level?.trim() || undefined,
    industry_id: v.industry_id?.trim() || null,
    headcount: Number(v.headcount),
    application_deadline: v.application_deadline
      ? new Date(v.application_deadline).toISOString()
      : null,
    visibility: v.visibility,
    candidate_requirements: pruneCandidateRequirements(candidateRequirements) ?? null,
    cv_language_required: v.cv_language_required,
    // Original-JD-language hint — sent only when the partner/AI set a concrete
    // value; undefined lets the backend auto-detect. Separate from
    // `cv_language_required` (the candidate's required CV language).
    language_code: v.language_code || undefined,
  };
  return body;
}

/** Convert an ISO datetime to the `datetime-local` input value (local tz). */
function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function detailToValues(job: OwnerJobDetail): JobFormValues {
  return {
    title: job.title,
    description: job.description,
    requirements: job.requirements ?? "",
    benefits: job.benefits ?? "",
    employment_type: job.employment_type as JobFormValues["employment_type"],
    location_type: job.location_type as JobFormValues["location_type"],
    location_city: job.location_city ?? "",
    location_country: job.location_country || "Vietnam",
    required_skills: job.required_skills.join(", "),
    preferred_skills: job.preferred_skills.join(", "),
    experience_min_years:
      job.experience_min_years != null ? String(job.experience_min_years) : "",
    experience_max_years:
      job.experience_max_years != null ? String(job.experience_max_years) : "",
    degree_required: job.degree_required ?? "",
    salary_is_disclosed: job.salary != null,
    salary_min: job.salary?.min != null ? String(job.salary.min) : "",
    salary_max: job.salary?.max != null ? String(job.salary.max) : "",
    salary_currency: job.salary?.currency ?? "VND",
    salary_mode: (job.salary_mode as JobFormValues["salary_mode"]) ?? JOB_FORM_DEFAULTS.salary_mode,
    salary_period: (job.salary_period as JobFormValues["salary_period"]) ?? JOB_FORM_DEFAULTS.salary_period,
    salary_gross_net: (job.salary_gross_net as JobFormValues["salary_gross_net"]) ?? JOB_FORM_DEFAULTS.salary_gross_net,
    experience_mode: (job.experience_mode as JobFormValues["experience_mode"]) ?? JOB_FORM_DEFAULTS.experience_mode,
    seniority_level: job.seniority_level ?? "",
    industry_id: job.industry_id ?? "",
    cv_language_required: (job.cv_language_required as JobFormValues["cv_language_required"]) ?? JOB_FORM_DEFAULTS.cv_language_required,
    language_code: normalizeLanguageCode(job.language_code),
    headcount: String(job.headcount ?? 1),
    application_deadline: toLocalInput(job.application_deadline),
    visibility: job.visibility,
  };
}

/**
 * Hydrate a CandidateRequirements object from a job detail for edit-mode.
 * Falls back to EMPTY_CANDIDATE_REQUIREMENTS when the job has none stored.
 * Exported for use by future F6 (CandidateRequirementsPanel) external state init.
 */
export function detailToCandidateRequirements(job: OwnerJobDetail): CandidateRequirements {
  if (!job.candidate_requirements) return EMPTY_CANDIDATE_REQUIREMENTS;
  return {
    ...EMPTY_CANDIDATE_REQUIREMENTS,
    ...job.candidate_requirements,
  };
}

// ---------------------------------------------------------------------------
// Component props
// ---------------------------------------------------------------------------

interface JobFormProps {
  mode: "create" | "edit";
  /** Existing job for edit mode (provides version + prefill). */
  job?: OwnerJobDetail;
  /**
   * JD quality-check findings for this job (only meaningful pre-submit, i.e.
   * `draft`/`rejected`). Rendered as scannable inline notes under the
   * matching field so partners fix issues where they occur, not just in a
   * toast (B-552 quality gate).
   */
  qualityIssues?: JobQualityIssue[];
  /**
   * Organization display name for the live preview pane. Pass from the
   * calling screen when available (e.g. from org profile query). When
   * undefined the preview omits the company name line.
   */
  companyName?: string;
  onSuccess: (job: OwnerJobDetail) => void;
  onCancel?: () => void;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function JobForm({ mode, job, qualityIssues, companyName, onSuccess, onCancel }: JobFormProps) {
  const t = useTranslations("jobs");
  const tf = useTranslations("jobs.form");
  const tv = useTranslations("jobs.validation");
  const tc = useTranslations("common");
  const toast = useToast();
  const getMessage = useApiErrorMessage();

  // Post-publication amendment policy (B-552): once a job is `active`, some
  // fields apply instantly (free-amend) and some pull the job back into
  // moderation (re-moderation).
  const isActive = job?.status === "active";

  // Multi-location state (independent of react-hook-form field array).
  const [locations, setLocations] = useState<JobLocationItem[]>(
    () => job?.locations ?? [],
  );

  // External eligibility state — mirrors the `locations` pattern.
  const [candidateReq, setCandidateReq] = useState<CandidateRequirements>(
    () => (job ? detailToCandidateRequirements(job) : EMPTY_CANDIDATE_REQUIREMENTS),
  );

  // Provenance chips — populated by JD auto-fill, cleared on field edit.
  const provenance = useProvenance();

  // Industry tree — share cache with IndustryPicker (same queryKey ["industries","tree"]).
  const industriesQuery = useQuery({
    queryKey: ["industries", "tree"],
    queryFn: () => searchApi.industryTree(),
    staleTime: 10 * 60 * 1000,
    retry: false,
  });
  const flatIndustries = useMemo(
    () => flattenIndustries(industriesQuery.data ?? []),
    [industriesQuery.data],
  );

  // Preview modal toggle
  const [previewOpen, setPreviewOpen] = useState(false);

  const [pendingRemoderation, setPendingRemoderation] = useState<{
    values: JobFormValues;
    fields: string[];
  } | null>(null);

  const {
    register,
    control,
    handleSubmit,
    setError,
    watch,
    setValue,
    formState: { errors, dirtyFields },
  } = useForm<JobFormValues>({
    resolver: zodResolver(jobFormSchema(tv)),
    defaultValues: job ? detailToValues(job) : JOB_FORM_DEFAULTS,
  });

  const salaryMode = watch("salary_mode");
  const experienceMode = watch("experience_mode");
  // All watched values for the live preview (read-only snapshot)
  const previewValues = watch();

  // ---------------------------------------------------------------------------
  // JD auto-fill handler
  // ---------------------------------------------------------------------------

  function handleJdExtracted(result: JdUploadResult) {
    // AI unavailable or not an AI extraction: keep raw-text fallback, do not prefill.
    if (result.status === "ai_unavailable" || !result.is_ai_extraction) {
      // Fallback toast is already shown by jd-upload-button; nothing to prefill.
      return;
    }

    // Track which provenance keys were set from the result.
    // Keys must match what the form's FieldProvenance chips use (see provenance.get(...) calls in the JSX).
    const provenanceMap: Record<string, "filled" | "review"> = {};

    function mark(key: string) {
      provenanceMap[key] = "filled";
    }

    // -----------------------------------------------------------------------
    // Existing field mappings (preserved)
    // -----------------------------------------------------------------------
    if (result.title) {
      setValue("title", result.title, { shouldDirty: true });
      mark("title");
    }
    const desc = result.description_vi || result.description_en;
    if (desc) {
      setValue("description", desc, { shouldDirty: true });
      mark("description");
    }
    const req = result.requirements_vi || result.requirements_en;
    if (req) {
      setValue("requirements", req, { shouldDirty: true });
      mark("requirements");
    }
    const ben = result.benefits_vi || result.benefits_en;
    if (ben) {
      setValue("benefits", ben, { shouldDirty: true });
      mark("benefits");
    }
    if (result.employment_type) {
      setValue("employment_type", result.employment_type as never, { shouldDirty: true });
      mark("employment_type");
    }
    if (result.required_skills?.length) {
      setValue("required_skills", result.required_skills.join(", "), { shouldDirty: true });
      mark("required_skills");
    }
    if (result.preferred_skills?.length) {
      setValue("preferred_skills", result.preferred_skills.join(", "), { shouldDirty: true });
      mark("preferred_skills");
    }
    if (result.experience_min_years != null) {
      setValue("experience_min_years", String(result.experience_min_years), { shouldDirty: true });
      mark("experience");
    }
    if (result.experience_max_years != null) {
      setValue("experience_max_years", String(result.experience_max_years), { shouldDirty: true });
      mark("experience");
    }
    if (result.headcount != null) {
      setValue("headcount", String(result.headcount), { shouldDirty: true });
      mark("headcount");
    }
    // Salary min/max/currency (keep existing mappings)
    if (result.salary_min != null) {
      setValue("salary_min", String(result.salary_min), { shouldDirty: true });
      mark("salary");
    }
    if (result.salary_max != null) {
      setValue("salary_max", String(result.salary_max), { shouldDirty: true });
      mark("salary");
    }
    if (result.salary_currency) {
      setValue("salary_currency", result.salary_currency, { shouldDirty: true });
      mark("salary");
    }

    // -----------------------------------------------------------------------
    // New field mappings (F8)
    // -----------------------------------------------------------------------

    // Salary mode, period, gross/net
    if (result.salary_mode) {
      setValue("salary_mode", result.salary_mode as JobFormValues["salary_mode"], { shouldDirty: true });
      mark("salary");
    }
    if (result.salary_period) {
      setValue("salary_period", result.salary_period as JobFormValues["salary_period"], { shouldDirty: true });
      mark("salary");
    }
    if (result.salary_gross_net) {
      setValue("salary_gross_net", result.salary_gross_net as JobFormValues["salary_gross_net"], { shouldDirty: true });
      mark("salary");
    }

    // Experience mode & seniority
    if (result.experience_mode) {
      setValue("experience_mode", result.experience_mode as JobFormValues["experience_mode"], { shouldDirty: true });
      mark("experience");
    }
    if (result.seniority_level) {
      setValue("seniority_level", result.seniority_level, { shouldDirty: true });
      mark("seniority_level");
    }

    // CV language requirement (extracted from JD language detection)
    if (result.cv_language_required) {
      setValue(
        "cv_language_required",
        result.cv_language_required as JobFormValues["cv_language_required"],
        { shouldDirty: true },
      );
      mark("cv_language_required");
    }

    // Original JD language (the language the JD text itself is written in).
    // Normalize the detector output: "mixed" -> "vi", "unknown"/other -> unset
    // (leave the field on "Auto-detect" so the backend resolves it). Distinct
    // from cv_language_required above.
    const detectedLang = normalizeLanguageCode(result.detected_language);
    if (detectedLang) {
      setValue("language_code", detectedLang, { shouldDirty: true });
      mark("language_code");
    }

    // Application deadline: convert ISO/date string to datetime-local format
    if (result.application_deadline) {
      const dlLocal = toLocalInput(result.application_deadline);
      if (dlLocal) {
        setValue("application_deadline", dlLocal, { shouldDirty: true });
        mark("application_deadline");
      }
    }

    // Multi-location prefill (now carries per-site `type`)
    if (result.locations?.length) {
      setLocations(result.locations.map((l) => ({
        type: l.type ?? result.location_type ?? "onsite",
        province_code: l.province_code ?? null,
        city: l.city ?? null,
        country: l.country || "Vietnam",
      })));
      mark("locations");
    } else if (result.location_type) {
      setLocations([{ type: result.location_type, province_code: null, city: null, country: "Vietnam" }]);
      mark("locations");
    }

    // Candidate requirements (merge over EMPTY so absent groups stay not_required)
    if (result.candidate_requirements) {
      setCandidateReq((prev) => ({
        ...EMPTY_CANDIDATE_REQUIREMENTS,
        ...prev,
        ...result.candidate_requirements,
        // Merge nested arrays defensively — prefer result values when present
        languages: result.candidate_requirements?.languages ?? prev.languages,
        certifications: result.candidate_requirements?.certifications ?? prev.certifications,
      }));
      mark("candidate_requirements");
    }

    // -----------------------------------------------------------------------
    // Industry auto-select from free-text name in the JD result.
    // Only sets when there is a genuine name match — never fabricates.
    // Mark as "review" so the partner can confirm or change the AI guess.
    // -----------------------------------------------------------------------
    if (result.industry && flatIndustries.length > 0) {
      const matched = matchIndustryByName(result.industry, flatIndustries);
      if (matched) {
        setValue("industry_id", matched.id, { shouldDirty: true });
        provenanceMap["industry_id"] = "review";
      }
    }

    // -----------------------------------------------------------------------
    // Provenance: override "filled" → "review" for fields flagged by confidence
    // -----------------------------------------------------------------------
    const confidence = result.field_confidence ?? {};
    for (const [field, conf] of Object.entries(confidence)) {
      if (conf.needs_review && provenanceMap[field] !== undefined) {
        provenanceMap[field] = "review";
      }
    }
    // candidate_requirements block-level review flag
    if (
      result.field_confidence?.candidate_requirements?.needs_review ||
      (result.needs_review && result.candidate_requirements)
    ) {
      provenanceMap["candidate_requirements"] = "review";
    }

    provenance.setAll(provenanceMap);

    // Success toast — "form pre-filled, check highlighted items"
    toast.show({ tone: "success", title: tf("uploadJdFilled") });
  }

  // ---------------------------------------------------------------------------
  // Mutation
  // ---------------------------------------------------------------------------

  const mutation = useMutation({
    mutationFn: (values: JobFormValues) => {
      const body = toBody(values, locations, candidateReq);
      return mode === "create"
        ? jobsApi.create(body)
        : jobsApi.update(job!.id, { ...body, version: job!.version });
    },
    onSuccess: (updated) => {
      toast.show({
        tone: "success",
        title: mode === "create" ? t("createdToast") : t("savedToast"),
      });
      onSuccess(updated);
    },
    onError: (e) => {
      if (applyFieldErrors(e, setError)) return;
      const reason =
        e instanceof ApiError && typeof e.details?.reason === "string"
          ? e.details.reason
          : undefined;
      if (
        reason === "version_conflict" ||
        (e instanceof ApiError && e.code === "CONFLICT")
      ) {
        toast.show({
          tone: "error",
          title: t("conflictToast"),
          description: t("conflictBody"),
        });
        return;
      }
      if (reason === "not_editable") {
        toast.show({ tone: "error", title: t("notEditableToast") });
        return;
      }
      toast.show({ tone: "error", title: getMessage(e) });
    },
  });

  // ---------------------------------------------------------------------------
  // Amendment change detection
  // ---------------------------------------------------------------------------

  /** Fields (RHF keys + standalone `locations` + `candidateReq`) actually changed. */
  function changedFields(): string[] {
    const dirty = Object.keys(dirtyFields);
    const locationsChanged =
      JSON.stringify(locations) !== JSON.stringify(job?.locations ?? []);
    const eligibilityChanged =
      JSON.stringify(candidateReq) !==
      JSON.stringify(detailToCandidateRequirements(job!));

    const extra: string[] = [];
    if (locationsChanged) extra.push("locations");
    if (eligibilityChanged && isActive) extra.push("candidate_requirements");
    return [...dirty, ...extra];
  }

  function onValidSubmit(values: JobFormValues) {
    if (isActive) {
      const remodFields = changedFields().filter(isRemoderationField);
      if (remodFields.length > 0) {
        setPendingRemoderation({ values, fields: [...new Set(remodFields)] });
        return;
      }
    }
    mutation.mutate(values);
  }

  function confirmRemoderationSubmit() {
    if (!pendingRemoderation) return;
    mutation.mutate(pendingRemoderation.values);
    setPendingRemoderation(null);
  }

  // ---------------------------------------------------------------------------
  // Options
  // ---------------------------------------------------------------------------

  const employmentOptions = EMPLOYMENT_TYPES.map((v) => ({
    value: v,
    label: t(`enums.employmentType.${v}`),
  }));
  const visibilityOptions = JOB_VISIBILITIES.map((v) => ({
    value: v,
    label: t(`enums.visibility.${v}`),
  }));

  const salaryModeOptions = (["negotiable", "range", "from", "to", "fixed", "hidden"] as const).map(
    (v) => ({ value: v, label: tf(`salaryModeOpts.${v}`) }),
  );
  const salaryPeriodOptions = (["monthly", "yearly"] as const).map((v) => ({
    value: v,
    label: tf(`salaryPeriodOpts.${v}`),
  }));
  const salaryGrossNetOptions = (["unspecified", "gross", "net"] as const).map((v) => ({
    value: v,
    label: tf(`salaryGrossNetOpts.${v}`),
  }));
  const experienceModeOptions = (
    ["no_requirement", "fresher", "min", "max", "range"] as const
  ).map((v) => ({ value: v, label: tf(`experienceModeOpts.${v}`) }));
  const seniorityOptions = [
    { value: "", label: tf("seniorityOpts.not_required") },
    ...(["intern", "fresher", "junior", "middle", "senior", "lead", "manager", "director", "executive"] as const).map(
      (v) => ({ value: v, label: tf(`seniorityOpts.${v}`) }),
    ),
  ];
  // Original-JD-language selector. "" = Auto-detect (maps to an undefined
  // `language_code`, letting the backend resolve it).
  const originalLanguageOptions = [
    { value: "", label: tf("originalLanguage.auto") },
    ...STORABLE_LANGUAGE_CODES.map((v) => ({
      value: v,
      label: tf(`originalLanguage.opts.${v}`),
    })),
  ];

  const requirementModeLabels = {
    notRequired: tf("eligibility.mode.notRequired"),
    required: tf("eligibility.mode.required"),
    preferred: tf("eligibility.mode.preferred"),
  };
  const ageModeLabels = {
    notRequired: tf("eligibility.age.notRequired"),
    atLeast: tf("eligibility.age.atLeast"),
    upTo: tf("eligibility.age.upTo"),
    range: tf("eligibility.age.range"),
    minLabel: tf("eligibility.age.minLabel"),
    maxLabel: tf("eligibility.age.maxLabel"),
  };
  const genderPresets = [
    { value: "male", label: tf("eligibility.genderPresets.male") },
    { value: "female", label: tf("eligibility.genderPresets.female") },
    { value: "other", label: tf("eligibility.genderPresets.other") },
  ];
  const maritalPresets = [
    { value: "single", label: tf("eligibility.maritalPresets.single") },
    { value: "married", label: tf("eligibility.maritalPresets.married") },
    { value: "other", label: tf("eligibility.maritalPresets.other") },
  ];

  // SalaryAmountInputs is defined at module level below (extracted to avoid
  // per-render function recreation) — wired via the salaryAmountInputsProps object.

  // ---------------------------------------------------------------------------
  // Salary amount inputs props (passed to module-level component)
  // ---------------------------------------------------------------------------

  const salaryAmountInputsProps = {
    salaryMode,
    register,
    errors,
    onClearProvenance: () => provenance.clear("salary"),
    isActive,
    minLabel: salaryMode === "fixed" ? tf("salaryFixedLabel") : tf("salaryFromLabel"),
    maxLabel: tf("salaryToLabel"),
  } as const;

  const headerActions =
    mode === "create" ? (
      <>
        <JdUploadButton
          onExtracted={handleJdExtracted}
          disabled={mutation.isPending}
          label={tf("uploadJdTitle")}
          showFileName={false}
        />
        <JdWriterButton
          jobId={job?.id}
          formInputs={{
            title: watch("title"),
            employment_type: watch("employment_type"),
            required_skills: watch("required_skills"),
            preferred_skills: watch("preferred_skills"),
          }}
          onAccept={(draft) => {
            setValue("description", draft, { shouldDirty: true });
            provenance.clear("description");
          }}
          shimmer
        />
        <Button
          variant="ghost"
          size="sm"
          type="button"
          onClick={() => setPreviewOpen(true)}
          className="size-10 rounded-full border border-[var(--border-default)] bg-white px-0 hover:bg-[var(--bg-subtle)]"
          aria-label={tf("previewToggle")}
          title={tf("previewToggle")}
        >
          <Eye aria-hidden weight="bold" className="size-4" />
        </Button>
      </>
    ) : undefined;

  return (
    <form
      className="w-full min-w-0 space-y-6"
      onSubmit={handleSubmit(onValidSubmit)}
      noValidate
    >
      {mode === "create" && (
        <PageHeader title={t("newJobTitle")} actions={headerActions} />
      )}

      <div className="w-full space-y-8">
        {isActive && (
          <div className="rounded-2xl border border-[var(--amber-600)]/40 bg-[var(--amber-100)] p-4 text-sm text-[var(--amber-700)]">
            <p className="font-semibold">{tf("amendment.bannerTitle")}</p>
            <p className="mt-1">{tf("amendment.bannerBody")}</p>
          </div>
        )}

        <div className="space-y-8">
          <Fieldset>
            <div className="xl:col-span-6">
              <div className="mb-1.5 flex items-center gap-2">
                <label
                  htmlFor="job-title"
                  className="text-sm font-semibold text-[var(--text-primary)]"
                >
                  {tf("title")}
                  <span aria-hidden className="ml-0.5 text-[var(--brand-red)]">*</span>
                </label>
                <FieldProvenance
                  state={provenance.get("title")}
                  label={provenance.get("title") === "filled" ? tf("provenance.filled") : tf("provenance.review")}
                  onClear={() => provenance.clear("title")}
                />
              </div>
              <Input
                id="job-title"
                required
                error={errors.title?.message}
                {...register("title", { onChange: () => provenance.clear("title") })}
              />
              {isActive && (
                <AmendTagInline kind="remoderation" label={tf("amendment.remoderationTag")} />
              )}
              <JdFieldIssueNote issues={qualityIssues} field="title" />
            </div>

            <div className="xl:col-span-2">
              <div className="mb-1.5 flex items-center gap-2">
                <span className="text-sm font-semibold text-[var(--text-primary)]">
                  {tf("employmentType")}
                  <span aria-hidden className="ml-0.5 text-[var(--brand-red)]">*</span>
                </span>
                <FieldProvenance
                  state={provenance.get("employment_type")}
                  label={provenance.get("employment_type") === "filled" ? tf("provenance.filled") : tf("provenance.review")}
                  onClear={() => provenance.clear("employment_type")}
                />
              </div>
              <Select
                required
                error={errors.employment_type?.message}
                options={employmentOptions}
                disabled={isActive}
                {...register("employment_type", { onChange: () => provenance.clear("employment_type") })}
              />
              {isActive && (
                <AmendTagInline kind="remoderation" label={tf("amendment.remoderationTag")} />
              )}
            </div>

            <div className="xl:col-span-2">
              <div className="mb-1.5 flex items-center gap-2">
                <span className="text-sm font-semibold text-[var(--text-primary)]">
                  {tf("industry")}
                </span>
                <FieldProvenance
                  state={provenance.get("industry_id")}
                  label={
                    provenance.get("industry_id") === "filled"
                      ? tf("provenance.filled")
                      : tf("provenance.review")
                  }
                  onClear={() => provenance.clear("industry_id")}
                />
              </div>
              <Controller
                control={control}
                name="industry_id"
                render={({ field }) => (
                  <IndustryPicker
                    value={field.value || null}
                    onChange={(id) => {
                      field.onChange(id ?? "");
                      provenance.clear("industry_id");
                    }}
                    disabled={isActive}
                    placeholder={tf("industryPlaceholder")}
                    searchPlaceholder={tf("industrySearchPlaceholder")}
                    emptyText={tf("industryEmpty")}
                    loadingText={tf("industryLoading")}
                  />
                )}
              />
              {isActive && (
                <AmendTagInline kind="remoderation" label={tf("amendment.remoderationTag")} />
              )}
            </div>

            <div className="xl:col-span-2">
              <div className="mb-1.5 flex items-center gap-2">
                <p className="text-sm font-medium text-[var(--text-primary)]">
                  {tf("locations")}
                  <span aria-hidden className="ml-1 text-[var(--brand-red)]">*</span>
                </p>
                <FieldProvenance
                  state={provenance.get("locations")}
                  label={provenance.get("locations") === "filled" ? tf("provenance.filled") : tf("provenance.review")}
                  onClear={() => provenance.clear("locations")}
                />
              </div>
              <JobLocationPicker
                value={locations}
                onChange={(v) => {
                  setLocations(v);
                  provenance.clear("locations");
                }}
                disabled={mutation.isPending}
              />
              {isActive && (
                <AmendTagInline kind="remoderation" label={tf("amendment.remoderationTag")} />
              )}
              <JdFieldIssueNote issues={qualityIssues} field="location_city" />
            </div>

            <div className="xl:col-span-2">
              <div className="mb-1.5 flex items-center gap-2">
                <label
                  htmlFor="job-language-code"
                  className="text-sm font-semibold text-[var(--text-primary)]"
                >
                  {tf("originalLanguage.label")}
                </label>
                <FieldProvenance
                  state={provenance.get("language_code")}
                  label={
                    provenance.get("language_code") === "filled"
                      ? tf("provenance.filled")
                      : tf("provenance.review")
                  }
                  onClear={() => provenance.clear("language_code")}
                />
              </div>
              <Controller
                control={control}
                name="language_code"
                render={({ field }) => (
                  <Select
                    id="job-language-code"
                    options={originalLanguageOptions}
                    help={tf("originalLanguage.help")}
                    value={field.value ?? ""}
                    onChange={(e) => {
                      const next = e.target.value;
                      field.onChange(
                        next === ""
                          ? undefined
                          : (next as JobFormValues["language_code"]),
                      );
                      provenance.clear("language_code");
                    }}
                  />
                )}
              />
              {isActive && (
                <AmendTagInline kind="free" label={tf("amendment.freeTag")} />
              )}
            </div>

            <div className="xl:col-span-6">
              <div className="mb-1.5 flex items-center gap-2">
                <span className="text-sm font-semibold text-[var(--text-primary)]">
                  {tf("description")}
                  <span aria-hidden className="ml-0.5 text-[var(--brand-red)]">*</span>
                </span>
                <FieldProvenance
                  state={provenance.get("description")}
                  label={provenance.get("description") === "filled" ? tf("provenance.filled") : tf("provenance.review")}
                  onClear={() => provenance.clear("description")}
                />
              </div>
              <Textarea
                id="job-description"
                aria-label={tf("description")}
                required
                rows={7}
                error={errors.description?.message}
                disabled={isActive}
                {...register("description", { onChange: () => provenance.clear("description") })}
              />
              {isActive && (
                <AmendTagInline kind="remoderation" label={tf("amendment.remoderationTag")} />
              )}
              <JdFieldIssueNote issues={qualityIssues} field="description" />
            </div>

            <div className="xl:col-span-3">
              <div className="mb-1.5 flex items-center gap-2">
                <span className="text-sm font-semibold text-[var(--text-primary)]">
                  {tf("requirements")}
                </span>
                <FieldProvenance
                  state={provenance.get("requirements")}
                  label={provenance.get("requirements") === "filled" ? tf("provenance.filled") : tf("provenance.review")}
                  onClear={() => provenance.clear("requirements")}
                />
              </div>
              <Textarea
                id="job-requirements"
                rows={5}
                error={errors.requirements?.message}
                disabled={isActive}
                {...register("requirements", { onChange: () => provenance.clear("requirements") })}
              />
              {isActive && (
                <AmendTagInline kind="remoderation" label={tf("amendment.remoderationTag")} />
              )}
              <JdFieldIssueNote issues={qualityIssues} field="requirements" />
            </div>

            <div className="xl:col-span-3">
              <div className="mb-1.5 flex items-center gap-2">
                <span className="text-sm font-semibold text-[var(--text-primary)]">
                  {tf("benefits")}
                </span>
                <FieldProvenance
                  state={provenance.get("benefits")}
                  label={provenance.get("benefits") === "filled" ? tf("provenance.filled") : tf("provenance.review")}
                  onClear={() => provenance.clear("benefits")}
                />
              </div>
              <Textarea
                id="job-benefits"
                aria-label={tf("benefits")}
                rows={5}
                error={errors.benefits?.message}
                {...register("benefits", { onChange: () => provenance.clear("benefits") })}
              />
              {isActive && (
                <AmendTagInline kind="free" label={tf("amendment.freeTag")} />
              )}
            </div>
          </Fieldset>

          <Fieldset>
            <div className="xl:col-span-3">
              <div className="mb-1.5 flex items-center gap-2">
                <span className="text-sm font-semibold text-[var(--text-primary)]">
                  {tf("requiredSkills")}
                </span>
                <FieldProvenance
                  state={provenance.get("required_skills")}
                  label={provenance.get("required_skills") === "filled" ? tf("provenance.filled") : tf("provenance.review")}
                  onClear={() => provenance.clear("required_skills")}
                />
              </div>
              <Input
                help={tf("skillsHelp")}
                error={errors.required_skills?.message}
                disabled={isActive}
                {...register("required_skills", { onChange: () => provenance.clear("required_skills") })}
              />
              {isActive && (
                <AmendTagInline kind="remoderation" label={tf("amendment.remoderationTag")} />
              )}
            </div>

            <div className="xl:col-span-3">
              <div className="mb-1.5 flex items-center gap-2">
                <span className="text-sm font-semibold text-[var(--text-primary)]">
                  {tf("preferredSkills")}
                </span>
                <FieldProvenance
                  state={provenance.get("preferred_skills")}
                  label={provenance.get("preferred_skills") === "filled" ? tf("provenance.filled") : tf("provenance.review")}
                  onClear={() => provenance.clear("preferred_skills")}
                />
              </div>
              <Input
                help={tf("skillsHelp")}
                error={errors.preferred_skills?.message}
                disabled={isActive}
                {...register("preferred_skills", { onChange: () => provenance.clear("preferred_skills") })}
              />
              {isActive && (
                <AmendTagInline kind="remoderation" label={tf("amendment.remoderationTag")} />
              )}
            </div>

            <div className="space-y-3 xl:col-span-4">
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-[var(--text-primary)]">
                    {tf("experienceMode")}
                  </span>
                  <FieldProvenance
                    state={provenance.get("experience")}
                    label={provenance.get("experience") === "filled" ? tf("provenance.filled") : tf("provenance.review")}
                    onClear={() => provenance.clear("experience")}
                  />
                </div>
                <Controller
                  control={control}
                  name="experience_mode"
                  render={({ field }) => (
                    <SegmentedControl
                      value={field.value}
                      onValueChange={(v) => {
                        field.onChange(v);
                        provenance.clear("experience");
                      }}
                      options={experienceModeOptions}
                      ariaLabel={tf("experienceMode")}
                      size="sm"
                      disabled={isActive}
                    />
                  )}
                />
              </div>
              <div className="flex flex-wrap gap-4">
                {(experienceMode === "min" || experienceMode === "range") && (
                  <div className="w-40">
                    <Input
                      label={tf("expMin")}
                      inputMode="numeric"
                      error={errors.experience_min_years?.message}
                      disabled={isActive}
                      {...register("experience_min_years", { onChange: () => provenance.clear("experience") })}
                    />
                  </div>
                )}
                {(experienceMode === "max" || experienceMode === "range") && (
                  <div className="w-40">
                    <Input
                      label={tf("expMax")}
                      inputMode="numeric"
                      error={errors.experience_max_years?.message}
                      disabled={isActive}
                      {...register("experience_max_years", { onChange: () => provenance.clear("experience") })}
                    />
                  </div>
                )}
              </div>
              {isActive && (
                <AmendTagInline kind="remoderation" label={tf("amendment.remoderationTag")} />
              )}
              <JdFieldIssueNote issues={qualityIssues} field="experience" />
            </div>

            <div className="xl:col-span-1">
              <div className="mb-1.5 flex items-center gap-2">
                <span className="text-sm font-semibold text-[var(--text-primary)]">
                  {tf("seniority")}
                </span>
                <FieldProvenance
                  state={provenance.get("seniority_level")}
                  label={provenance.get("seniority_level") === "filled" ? tf("provenance.filled") : tf("provenance.review")}
                  onClear={() => provenance.clear("seniority_level")}
                />
              </div>
              <Select
                options={seniorityOptions}
                error={errors.seniority_level?.message}
                disabled={isActive}
                {...register("seniority_level", { onChange: () => provenance.clear("seniority_level") })}
              />
              {isActive && (
                <AmendTagInline kind="remoderation" label={tf("amendment.remoderationTag")} />
              )}
            </div>

            <div className="xl:col-span-1">
              <Input
                label={tf("degree")}
                error={errors.degree_required?.message}
                disabled={isActive}
                {...register("degree_required")}
              />
            </div>
          </Fieldset>

          <Fieldset>
            <div className="space-y-3 xl:col-span-6">
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-[var(--text-primary)]">
                    {tf("salaryMode")}
                  </span>
                  <FieldProvenance
                    state={provenance.get("salary")}
                    label={provenance.get("salary") === "filled" ? tf("provenance.filled") : tf("provenance.review")}
                    onClear={() => provenance.clear("salary")}
                  />
                </div>
                <Controller
                  control={control}
                  name="salary_mode"
                  render={({ field }) => (
                    <SegmentedControl
                      value={field.value}
                      onValueChange={(v) => {
                        field.onChange(v);
                        provenance.clear("salary");
                      }}
                      options={salaryModeOptions}
                      ariaLabel={tf("salaryMode")}
                      size="sm"
                      disabled={isActive}
                    />
                  )}
                />
              </div>

              {salaryMode === "hidden" && (
                <p className="text-xs text-[var(--text-muted)]">{tf("salaryHiddenHelp")}</p>
              )}

              <SalaryAmountInputsPanel {...salaryAmountInputsProps} />

              {(salaryMode === "range" || salaryMode === "from" || salaryMode === "to" || salaryMode === "fixed" || salaryMode === "hidden") && (
                <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                  <Select
                    label={tf("salaryPeriod")}
                    options={salaryPeriodOptions}
                    disabled={isActive}
                    {...register("salary_period")}
                  />
                  <Select
                    label={tf("salaryGrossNet")}
                    options={salaryGrossNetOptions}
                    disabled={isActive}
                    {...register("salary_gross_net")}
                  />
                  <Input
                    label={tf("currency")}
                    error={errors.salary_currency?.message}
                    disabled={isActive}
                    {...register("salary_currency")}
                  />
                </div>
              )}

              {isActive && (
                <AmendTagInline kind="remoderation" label={tf("amendment.remoderationTag")} />
              )}
              <JdFieldIssueNote issues={qualityIssues} field="salary" />
            </div>

            <div className="xl:col-span-2">
              <div className="mb-1.5 flex items-center gap-2">
                <span className="text-sm font-semibold text-[var(--text-primary)]">
                  {tf("headcount")}
                  <span aria-hidden className="ml-0.5 text-[var(--brand-red)]">*</span>
                </span>
                <FieldProvenance
                  state={provenance.get("headcount")}
                  label={provenance.get("headcount") === "filled" ? tf("provenance.filled") : tf("provenance.review")}
                  onClear={() => provenance.clear("headcount")}
                />
              </div>
              <Input
                required
                inputMode="numeric"
                error={errors.headcount?.message}
                {...register("headcount", { onChange: () => provenance.clear("headcount") })}
              />
              {isActive && <AmendTagInline kind="free" label={tf("amendment.freeTag")} />}
            </div>

            <div className="xl:col-span-2">
              <div className="mb-1.5 flex items-center gap-2">
                <span className="text-sm font-semibold text-[var(--text-primary)]">
                  {tf("deadline")}
                </span>
                <FieldProvenance
                  state={provenance.get("application_deadline")}
                  label={provenance.get("application_deadline") === "filled" ? tf("provenance.filled") : tf("provenance.review")}
                  onClear={() => provenance.clear("application_deadline")}
                />
              </div>
              <Input
                type="datetime-local"
                help={tf("deadlineHelp")}
                error={errors.application_deadline?.message}
                {...register("application_deadline", { onChange: () => provenance.clear("application_deadline") })}
              />
              {isActive && <AmendTagInline kind="free" label={tf("amendment.freeTag")} />}
            </div>

            <div className="xl:col-span-2">
              <Select
                label={tf("visibility")}
                help={tf("visibilityHelp")}
                error={errors.visibility?.message}
                options={visibilityOptions}
                {...register("visibility")}
              />
              {isActive && <AmendTagInline kind="free" label={tf("amendment.freeTag")} />}
            </div>
          </Fieldset>

          <Fieldset>
            {provenance.get("candidate_requirements") !== null && (
              <div className="xl:col-span-6 flex items-center gap-2">
                <FieldProvenance
                  state={provenance.get("candidate_requirements")}
                  label={
                    provenance.get("candidate_requirements") === "filled"
                      ? tf("provenance.filled")
                      : tf("provenance.eligibilityReview")
                  }
                  onClear={() => provenance.clear("candidate_requirements")}
                />
              </div>
            )}

            <div className="xl:col-span-6 grid gap-5 2xl:grid-cols-[1.3fr_1fr]">
              <EligibilityPanel
                title={tf("eligibility.panels.profile")}
              >
                <div className="grid gap-4 md:grid-cols-2">
                  <EligibilityFieldCard>
                    <RequirementGroupField
                      label={tf("eligibility.gender")}
                      value={candidateReq.gender ?? { mode: "not_required", values: [] }}
                      onChange={(v) => setCandidateReq((prev) => ({ ...prev, gender: v }))}
                      presets={genderPresets}
                      modeLabels={requirementModeLabels}
                      disabled={isActive}
                    />
                  </EligibilityFieldCard>
                  <EligibilityFieldCard>
                    <AgeRequirementField
                      label={tf("eligibility.ageLabel")}
                      value={candidateReq.age ?? { mode: "not_required" }}
                      onChange={(v) => setCandidateReq((prev) => ({ ...prev, age: v }))}
                      modeLabels={ageModeLabels}
                      disabled={isActive}
                    />
                  </EligibilityFieldCard>
                  <EligibilityFieldCard>
                    <RequirementGroupField
                      label={tf("eligibility.marital")}
                      value={candidateReq.marital_status ?? { mode: "not_required", values: [] }}
                      onChange={(v) => setCandidateReq((prev) => ({ ...prev, marital_status: v }))}
                      presets={maritalPresets}
                      modeLabels={requirementModeLabels}
                      disabled={isActive}
                    />
                  </EligibilityFieldCard>
                  <EligibilityFieldCard>
                    <RequirementGroupField
                      label={tf("eligibility.nationality")}
                      value={candidateReq.nationalities ?? { mode: "not_required", values: [] }}
                      onChange={(v) => setCandidateReq((prev) => ({ ...prev, nationalities: v }))}
                      modeLabels={requirementModeLabels}
                      disabled={isActive}
                    />
                  </EligibilityFieldCard>
                </div>
                <EligibilityFieldCard>
                  <RequirementGroupField
                    label={tf("eligibility.education")}
                    value={candidateReq.education ?? { mode: "not_required", values: [] }}
                    onChange={(v) => setCandidateReq((prev) => ({ ...prev, education: v }))}
                    modeLabels={requirementModeLabels}
                    disabled={isActive}
                  />
                </EligibilityFieldCard>
              </EligibilityPanel>

              <EligibilityPanel
                title={tf("eligibility.panels.credentials")}
              >
                <div className="space-y-4">
                  <EligibilityFieldCard>
                    <div className="mb-4 space-y-2">
                      <p className="text-sm font-semibold text-[var(--text-primary)]">
                        {tf("eligibility.cvLanguageRequired")}
                      </p>
                      <p className="text-xs text-[var(--text-muted)]">
                        {tf("eligibility.cvLanguageRequiredHelp")}
                      </p>
                      <Controller
                        control={control}
                        name="cv_language_required"
                        render={({ field }) => (
                          <SegmentedControl
                            value={field.value}
                            onValueChange={(v) => field.onChange(v)}
                            options={[
                              { value: "any", label: tf("eligibility.cvLang.any") },
                              { value: "en", label: tf("eligibility.cvLang.en") },
                              { value: "vi", label: tf("eligibility.cvLang.vi") },
                            ]}
                            ariaLabel={tf("eligibility.cvLanguageRequired")}
                            size="sm"
                            disabled={isActive}
                          />
                        )}
                      />
                    </div>
                  </EligibilityFieldCard>

                  <EligibilityFieldCard>
                    <p className="mb-2 text-sm font-semibold text-[var(--text-primary)]">
                      {tf("eligibility.languages")}
                    </p>
                    <LanguageRows
                      value={candidateReq.languages ?? []}
                      onChange={(v) => setCandidateReq((prev) => ({ ...prev, languages: v }))}
                      disabled={isActive}
                      labels={{
                        language: tf("eligibility.language.language"),
                        proficiency: tf("eligibility.language.proficiency"),
                        required: tf("eligibility.language.required"),
                        addRow: tf("eligibility.language.addRow"),
                      }}
                    />
                  </EligibilityFieldCard>

                  <EligibilityFieldCard>
                    <p className="mb-2 text-sm font-semibold text-[var(--text-primary)]">
                      {tf("eligibility.certifications")}
                    </p>
                    <CertificationRows
                      value={candidateReq.certifications ?? []}
                      onChange={(v) => setCandidateReq((prev) => ({ ...prev, certifications: v }))}
                      disabled={isActive}
                      labels={{
                        name: tf("eligibility.certification.name"),
                        required: tf("eligibility.certification.required"),
                        addRow: tf("eligibility.certification.addRow"),
                      }}
                    />
                  </EligibilityFieldCard>

                  <EligibilityFieldCard>
                    <Textarea
                      id="eligibility-note"
                      label={tf("eligibility.note")}
                      placeholder={tf("eligibility.notePlaceholder")}
                      rows={3}
                      value={candidateReq.note ?? ""}
                      onChange={(e) =>
                        setCandidateReq((prev) => ({ ...prev, note: e.target.value || null }))
                      }
                      disabled={isActive}
                    />
                  </EligibilityFieldCard>
                </div>
              </EligibilityPanel>
            </div>
          </Fieldset>
        </div>

        <div className="sticky bottom-0 z-10 border-t border-[var(--border-default)] bg-[var(--surface-card,#ffffff)]/96 py-4 backdrop-blur">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              {onCancel && (
                <Button
                  variant="ghost"
                  size="sm"
                  type="button"
                  onClick={onCancel}
                  disabled={mutation.isPending}
                >
                  {tc("cancel")}
                </Button>
              )}
            </div>

            <div className="ml-auto flex items-center gap-2">
              <Button type="submit" variant="primary" size="sm" loading={mutation.isPending}>
                <FloppyDisk aria-hidden weight="bold" className="size-4" />
                {mode === "create" ? tf("saveDraft") : tc("save")}
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Explicit confirmation before a live job's content amendment unpublishes
          it back to pending_review (B-552). */}
      <Modal
        open={pendingRemoderation !== null}
        onClose={() => setPendingRemoderation(null)}
        title={tf("amendment.confirmTitle")}
        description={tf("amendment.confirmBody")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setPendingRemoderation(null)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="primary"
              loading={mutation.isPending}
              onClick={confirmRemoderationSubmit}
            >
              {tf("amendment.confirmCta")}
            </Button>
          </>
        }
      >
        <ul className="list-disc space-y-1 pl-5 text-sm text-[var(--text-secondary)]">
          {(pendingRemoderation?.fields ?? []).map((f) => (
            <li key={f}>{amendmentFieldName(tf, f)}</li>
          ))}
        </ul>
      </Modal>

      <Modal
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
        title={tf("previewPaneTitle")}
        size="lg"
        closeLabel={tc("close")}
      >
        <JobPreview
          values={previewValues}
          locations={locations}
          candidateReq={candidateReq}
          companyName={companyName}
        />
      </Modal>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * Module-level salary amount inputs — extracted from inside JobForm to avoid
 * per-render function recreation (React treats inner function components as
 * new components every render, forcing full remounts on each keystroke).
 */
interface SalaryAmountInputsPanelProps {
  salaryMode: JobFormValues["salary_mode"];
  register: UseFormRegister<JobFormValues>;
  errors: FieldErrors<JobFormValues>;
  onClearProvenance: () => void;
  isActive: boolean;
  minLabel: string;
  maxLabel: string;
}

function SalaryAmountInputsPanel({
  salaryMode,
  register,
  errors,
  onClearProvenance,
  isActive,
  minLabel,
  maxLabel,
}: SalaryAmountInputsPanelProps) {
  const showMin = salaryMode === "range" || salaryMode === "from" || salaryMode === "fixed" || salaryMode === "hidden";
  const showMax = salaryMode === "range" || salaryMode === "to" || salaryMode === "hidden";

  if (!showMin && !showMax) return null;
  return (
    <div className="flex flex-wrap gap-4">
      {showMin && (
        <div className="w-40 min-w-[140px]">
          <Input
            label={minLabel}
            inputMode="numeric"
            error={errors.salary_min?.message}
            disabled={isActive}
            {...register("salary_min", {
              onChange: onClearProvenance,
            })}
          />
        </div>
      )}
      {showMax && (
        <div className="w-40 min-w-[140px]">
          <Input
            label={maxLabel}
            inputMode="numeric"
            error={errors.salary_max?.message}
            disabled={isActive}
            {...register("salary_max", {
              onChange: onClearProvenance,
            })}
          />
        </div>
      )}
    </div>
  );
}

/** Small inline badge marking a field as "quick edit" vs "requires re-review". */
function AmendTagInline({
  kind,
  label,
}: {
  kind: "free" | "remoderation";
  label: string;
}) {
  return (
    <p
      className={cn(
        "mt-1 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold",
        kind === "free"
          ? "bg-[var(--teal-50)] text-[var(--teal-700)]"
          : "bg-[var(--amber-100)] text-[var(--amber-700)]",
      )}
    >
      {label}
    </p>
  );
}

function Fieldset(props: {
  legend?: string;
  children: React.ReactNode;
  gridClassName?: string;
}) {
  const { legend, children, gridClassName } = props;
  return (
    <fieldset className="space-y-5 border-t border-[var(--border-default)] pt-6 first:border-t-0 first:pt-0">
      {legend ? (
        <legend className="px-0 text-[1rem] font-semibold tracking-tight text-[var(--text-primary)]">
          {legend}
        </legend>
      ) : null}
      <div
        className={
          gridClassName ??
          "grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-6 xl:gap-x-6 xl:gap-y-5"
        }
      >
        {children}
      </div>
    </fieldset>
  );
}

function EligibilityPanel({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-[28px] border border-[var(--border-default)] bg-[var(--surface-secondary)]/78 p-5 shadow-[0_16px_40px_rgba(15,23,42,0.05)]">
      <div className="mb-4 flex items-center gap-3">
        <div className="h-8 w-1 rounded-full bg-[var(--brand-primary)]" />
        <h3 className="text-sm font-semibold tracking-tight text-[var(--text-primary)]">
          {title}
        </h3>
      </div>
      {children}
    </section>
  );
}

function EligibilityFieldCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-4">
      {children}
    </div>
  );
}

// Keep backward-compat export used by the local Textarea in the old form.
// Now that we use the ui/Textarea directly, this is intentionally removed.
// (The ui Textarea is a forwardRef component and doesn't need a local wrapper.)

// Local Textarea wrapper was removed — using ui/Textarea directly.
// This comment preserves the intent for future readers.
export type { UseFormRegisterReturn };
