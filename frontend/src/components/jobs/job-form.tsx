"use client";

import { useState } from "react";
import {
  useForm,
  useFieldArray,
  Controller,
  type UseFormRegisterReturn,
} from "react-hook-form";
import { useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import {
  Plus,
  Trash,
  FloppyDisk,
  FileArrowUp,
  LockSimple,
} from "@phosphor-icons/react";
import { JobLocationPicker } from "./location-picker";
import type { JobLocationItem } from "@/lib/api/jobs";
import {
  Button,
  Input,
  Select,
  Switch,
  Modal,
  useToast,
} from "@/components/ui";
import { zodResolver } from "@/lib/validation/resolver";
import {
  jobFormSchema,
  JOB_FORM_DEFAULTS,
  type JobFormValues,
} from "@/lib/validation/jobs";
import { useApiErrorMessage, applyFieldErrors } from "@/lib/auth/use-api-error";
import { parseTags } from "@/lib/jobs/format";
import {
  ApiError,
  jobsApi,
  EMPLOYMENT_TYPES,
  JOB_VISIBILITIES,
  SCREENING_Q_TYPES,
  type JobCreateBody,
  type JobQualityIssue,
  type OwnerJobDetail,
} from "@/lib/api";
import { JdWriterButton } from "./jd-writer-button";
import { JdUploadButton } from "./jd-upload-button";
import { JdFieldIssueNote } from "./jd-quality-panel";
import type { JdUploadResult } from "@/lib/api/jobs";
import { isRemoderationField } from "@/lib/jobs/amendment";
import { cn } from "@/lib/utils";

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
  ]);
  return known.has(field) ? tf(`amendment.fieldNames.${field}`) : field;
}

function toBody(
  v: JobFormValues,
  locations: JobLocationItem[],
  opts: { includeScreening: boolean },
): JobCreateBody {
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
    salary_is_disclosed: v.salary_is_disclosed,
    salary_min: v.salary_is_disclosed && v.salary_min ? Number(v.salary_min) : null,
    salary_max: v.salary_is_disclosed && v.salary_max ? Number(v.salary_max) : null,
    salary_currency: v.salary_currency.trim() || "VND",
    headcount: Number(v.headcount),
    application_deadline: v.application_deadline
      ? new Date(v.application_deadline).toISOString()
      : null,
    visibility: v.visibility,
  };
  // Screening questions are locked once a job is `active` (B-552) — omitting
  // the key entirely (rather than sending the unchanged list) is required so
  // the backend does not reject the whole PATCH as a screening-edit attempt.
  if (opts.includeScreening) {
    body.screening_questions = v.screening_questions.map((q, i) => ({
      question: q.question.trim(),
      q_type: q.q_type,
      options:
        q.q_type === "single_choice" || q.q_type === "multiple_choice"
          ? parseTags(q.options)
          : null,
      is_required: q.is_required,
      sort_order: i,
    }));
  }
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
    headcount: String(job.headcount ?? 1),
    application_deadline: toLocalInput(job.application_deadline),
    visibility: job.visibility,
    screening_questions: job.screening_questions.map((q) => ({
      question: q.question,
      q_type: q.q_type,
      options: q.options?.join(", ") ?? "",
      is_required: q.is_required,
    })),
  };
}

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
  onSuccess: (job: OwnerJobDetail) => void;
  onCancel?: () => void;
}

export function JobForm({ mode, job, qualityIssues, onSuccess, onCancel }: JobFormProps) {
  const t = useTranslations("jobs");
  const tf = useTranslations("jobs.form");
  const tv = useTranslations("jobs.validation");
  const tc = useTranslations("common");
  const toast = useToast();
  const getMessage = useApiErrorMessage();

  // Post-publication amendment policy (B-552): once a job is `active`, some
  // fields apply instantly (free-amend) and some pull the job back into
  // moderation (re-moderation); screening questions become read-only.
  const isActive = job?.status === "active";

  // Multi-location state (independent of react-hook-form field array).
  const [locations, setLocations] = useState<JobLocationItem[]>(
    () => job?.locations ?? []
  );
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

  const { fields, append, remove } = useFieldArray({
    control,
    name: "screening_questions",
  });

  const salaryDisclosed = watch("salary_is_disclosed");

  function handleJdExtracted(result: JdUploadResult) {
    if (!result.is_ai_extraction) return; // fallback: user can read raw_text_preview manually
    if (result.title) setValue("title", result.title, { shouldDirty: true });
    const desc = result.description_vi || result.description_en;
    if (desc) setValue("description", desc, { shouldDirty: true });
    const req = result.requirements_vi || result.requirements_en;
    if (req) setValue("requirements", req, { shouldDirty: true });
    const ben = result.benefits_vi || result.benefits_en;
    if (ben) setValue("benefits", ben, { shouldDirty: true });
    if (result.employment_type) setValue("employment_type", result.employment_type as never, { shouldDirty: true });
    if (result.required_skills?.length) setValue("required_skills", result.required_skills.join(", "), { shouldDirty: true });
    if (result.preferred_skills?.length) setValue("preferred_skills", result.preferred_skills.join(", "), { shouldDirty: true });
    if (result.experience_min_years != null) setValue("experience_min_years", String(result.experience_min_years), { shouldDirty: true });
    if (result.experience_max_years != null) setValue("experience_max_years", String(result.experience_max_years), { shouldDirty: true });
    if (result.headcount != null) setValue("headcount", String(result.headcount), { shouldDirty: true });
    if (result.salary_is_disclosed) setValue("salary_is_disclosed", true, { shouldDirty: true });
    if (result.salary_min != null) setValue("salary_min", String(result.salary_min), { shouldDirty: true });
    if (result.salary_max != null) setValue("salary_max", String(result.salary_max), { shouldDirty: true });
    if (result.salary_currency) setValue("salary_currency", result.salary_currency, { shouldDirty: true });
    // Multi-location prefill
    if (result.locations?.length) {
      setLocations(result.locations.map((l) => ({
        type: result.location_type ?? "onsite",
        province_code: null,
        city: l.city ?? null,
        country: l.country || "Vietnam",
      })));
    } else if (result.location_type) {
      setLocations([{ type: result.location_type, province_code: null, city: null, country: "Vietnam" }]);
    }
  }

  const mutation = useMutation({
    mutationFn: (values: JobFormValues) => {
      const body = toBody(values, locations, { includeScreening: !isActive });
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
      if (reason === "screening_locked_after_publish") {
        toast.show({ tone: "error", title: tf("amendment.screeningLockedToast") });
        return;
      }
      toast.show({ tone: "error", title: getMessage(e) });
    },
  });

  /** Fields (RHF keys + the standalone `locations` picker) actually changed. */
  function changedFields(): string[] {
    const dirty = Object.keys(dirtyFields).filter(
      (f) => f !== "screening_questions",
    );
    const locationsChanged =
      JSON.stringify(locations) !== JSON.stringify(job?.locations ?? []);
    return locationsChanged ? [...dirty, "locations"] : dirty;
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

  const employmentOptions = EMPLOYMENT_TYPES.map((v) => ({
    value: v,
    label: t(`enums.employmentType.${v}`),
  }));
  const visibilityOptions = JOB_VISIBILITIES.map((v) => ({
    value: v,
    label: t(`enums.visibility.${v}`),
  }));

  return (
    <form
      className="space-y-8"
      onSubmit={handleSubmit(onValidSubmit)}
      noValidate
    >
      {/* Post-publication amendment policy banner (B-552) */}
      {isActive && (
        <div className="rounded-2xl border border-[var(--amber-600)]/40 bg-[var(--amber-100)] p-4 text-sm text-[var(--amber-700)]">
          <p className="font-semibold">{tf("amendment.bannerTitle")}</p>
          <p className="mt-1">{tf("amendment.bannerBody")}</p>
        </div>
      )}

      {/* Basics */}
      {/* JD Upload — prefills all form fields from uploaded PDF/DOCX */}
      <div className="flex items-center gap-3 rounded-2xl border border-teal-500/20 bg-gradient-to-br from-teal-50/60 to-white/60 px-4 py-3.5 shadow-[0_2px_12px_rgba(20,184,166,0.06)]">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg icon-chip-success shadow-sm">
          <FileArrowUp aria-hidden weight="duotone" className="size-4 text-white" />
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            {tf("uploadJdTitle")}
          </p>
          <p className="text-xs text-[var(--text-muted)]">{tf("uploadJdHint")}</p>
        </div>
        <JdUploadButton onExtracted={handleJdExtracted} disabled={mutation.isPending} />
      </div>

      <Fieldset legend={tf("basicsLegend")}>
        <div>
          <Input
            label={tf("title")}
            required
            error={errors.title?.message}
            {...register("title")}
          />
          {isActive && (
            <AmendTagInline kind="remoderation" label={tf("amendment.remoderationTag")} />
          )}
          <JdFieldIssueNote issues={qualityIssues} field="title" />
        </div>
        <div>
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <span className="text-sm font-medium text-[var(--text-primary)]">
              {tf("description")}
              <span aria-hidden className="ml-0.5 text-[var(--brand-red)]">*</span>
            </span>
            <JdWriterButton
              jobId={job?.id}
              formInputs={{
                title: watch("title"),
                employment_type: watch("employment_type"),
                required_skills: watch("required_skills"),
                preferred_skills: watch("preferred_skills"),
              }}
              onAccept={(draft) => setValue("description", draft, { shouldDirty: true })}
            />
          </div>
          <Textarea
            id="job-description"
            label=""
            aria-label={tf("description")}
            required
            rows={6}
            error={errors.description?.message}
            register={register("description")}
          />
          {isActive && (
            <AmendTagInline kind="remoderation" label={tf("amendment.remoderationTag")} />
          )}
          <JdFieldIssueNote issues={qualityIssues} field="description" />
        </div>
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <div>
            <Select
              label={tf("employmentType")}
              required
              error={errors.employment_type?.message}
              options={employmentOptions}
              {...register("employment_type")}
            />
            {isActive && (
              <AmendTagInline kind="remoderation" label={tf("amendment.remoderationTag")} />
            )}
          </div>
          <div className="col-span-full">
            <p className="mb-1.5 text-sm font-medium text-[var(--text-primary)]">
              {tf("locations")}
              <span aria-hidden className="ml-1 text-[var(--brand-red)]">*</span>
            </p>
            <JobLocationPicker
              value={locations}
              onChange={setLocations}
              disabled={mutation.isPending}
            />
            {isActive && (
              <AmendTagInline kind="remoderation" label={tf("amendment.remoderationTag")} />
            )}
            <JdFieldIssueNote issues={qualityIssues} field="location_city" />
          </div>
        </div>
      </Fieldset>

      {/* Details */}
      <Fieldset legend={tf("detailsLegend")}>
        <div>
          <Textarea
            id="job-requirements"
            label={tf("requirements")}
            rows={4}
            error={errors.requirements?.message}
            register={register("requirements")}
          />
          {isActive && (
            <AmendTagInline kind="remoderation" label={tf("amendment.remoderationTag")} />
          )}
          <JdFieldIssueNote issues={qualityIssues} field="requirements" />
        </div>
        <div>
          <Textarea
            id="job-benefits"
            label={tf("benefits")}
            rows={4}
            error={errors.benefits?.message}
            register={register("benefits")}
          />
          {isActive && (
            <AmendTagInline kind="free" label={tf("amendment.freeTag")} />
          )}
        </div>
        <div>
          <Input
            label={tf("requiredSkills")}
            help={tf("skillsHelp")}
            error={errors.required_skills?.message}
            {...register("required_skills")}
          />
          {isActive && (
            <AmendTagInline kind="remoderation" label={tf("amendment.remoderationTag")} />
          )}
        </div>
        <div>
          <Input
            label={tf("preferredSkills")}
            help={tf("skillsHelp")}
            error={errors.preferred_skills?.message}
            {...register("preferred_skills")}
          />
          {isActive && (
            <AmendTagInline kind="remoderation" label={tf("amendment.remoderationTag")} />
          )}
        </div>
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
          <div className="sm:col-span-2 grid grid-cols-2 gap-5">
            <Input
              label={tf("expMin")}
              inputMode="numeric"
              error={errors.experience_min_years?.message}
              {...register("experience_min_years")}
            />
            <Input
              label={tf("expMax")}
              inputMode="numeric"
              error={errors.experience_max_years?.message}
              {...register("experience_max_years")}
            />
          </div>
          <Input
            label={tf("degree")}
            error={errors.degree_required?.message}
            {...register("degree_required")}
          />
        </div>
        {isActive && (
          <AmendTagInline kind="remoderation" label={tf("amendment.remoderationTag")} />
        )}
        <JdFieldIssueNote issues={qualityIssues} field="experience" />
      </Fieldset>

      {/* Compensation & logistics */}
      <Fieldset legend={tf("compLegend")}>
        <Controller
          control={control}
          name="salary_is_disclosed"
          render={({ field }) => (
            <Switch
              id="salary-disclosed"
              label={tf("discloseSalary")}
              checked={field.value}
              onCheckedChange={field.onChange}
            />
          )}
        />
        {salaryDisclosed && (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
            <Input
              label={tf("salaryMin")}
              inputMode="numeric"
              error={errors.salary_min?.message}
              {...register("salary_min")}
            />
            <Input
              label={tf("salaryMax")}
              inputMode="numeric"
              error={errors.salary_max?.message}
              {...register("salary_max")}
            />
            <Input
              label={tf("currency")}
              error={errors.salary_currency?.message}
              {...register("salary_currency")}
            />
          </div>
        )}
        {isActive && (
          <AmendTagInline kind="remoderation" label={tf("amendment.remoderationTag")} />
        )}
        <JdFieldIssueNote issues={qualityIssues} field="salary" />
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <div>
            <Input
              label={tf("headcount")}
              required
              inputMode="numeric"
              error={errors.headcount?.message}
              {...register("headcount")}
            />
            {isActive && (
              <AmendTagInline kind="free" label={tf("amendment.freeTag")} />
            )}
          </div>
          <div>
            <Input
              type="datetime-local"
              label={tf("deadline")}
              help={tf("deadlineHelp")}
              error={errors.application_deadline?.message}
              {...register("application_deadline")}
            />
            {isActive && (
              <AmendTagInline kind="free" label={tf("amendment.freeTag")} />
            )}
          </div>
        </div>
        <div>
          <Select
            label={tf("visibility")}
            help={tf("visibilityHelp")}
            error={errors.visibility?.message}
            options={visibilityOptions}
            {...register("visibility")}
          />
          {isActive && (
            <AmendTagInline kind="free" label={tf("amendment.freeTag")} />
          )}
        </div>
      </Fieldset>

      {/* Screening questions — locked once the job is active (B-552): existing
          applications' screening_answers reference this question set by
          id/order, so mutating it post-publish would corrupt those answers. */}
      <Fieldset
        legend={tf("screeningLegend")}
        description={isActive ? undefined : tf("screeningHelp")}
      >
        {isActive && (
          <div className="flex items-start gap-2.5 rounded-xl border border-[var(--border-default)] bg-[var(--bg-subtle)] px-3.5 py-3">
            <LockSimple aria-hidden weight="bold" className="mt-0.5 size-4 shrink-0 text-[var(--text-muted)]" />
            <p className="text-sm text-[var(--text-secondary)]">
              {tf("amendment.screeningLockedNote")}
            </p>
          </div>
        )}
        {fields.length === 0 && (
          <p className="text-sm text-[var(--text-muted)]">{tf("noScreening")}</p>
        )}
        <ul className="space-y-4">
          {fields.map((f, i) => {
            const qType = watch(`screening_questions.${i}.q_type`);
            const showOptions =
              qType === "single_choice" || qType === "multiple_choice";
            return (
              <li
                key={f.id}
                className="rounded-xl border border-[var(--border-default)] bg-white p-4 "
              >
                <div className="mb-3 flex items-center justify-between">
                  <span className="text-sm font-semibold text-[var(--text-primary)]">
                    {tf("questionN", { n: i + 1 })}
                  </span>
                  {!isActive && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => remove(i)}
                      aria-label={tf("removeQuestion")}
                    >
                      <Trash aria-hidden weight="bold" className="size-4" />
                    </Button>
                  )}
                </div>
                <div className="space-y-3">
                  <Input
                    label={tf("questionText")}
                    disabled={isActive}
                    error={errors.screening_questions?.[i]?.question?.message}
                    {...register(`screening_questions.${i}.question`)}
                  />
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <Select
                      label={tf("questionType")}
                      disabled={isActive}
                      options={SCREENING_Q_TYPES.map((v) => ({
                        value: v,
                        label: t(`enums.screeningType.${v}`),
                      }))}
                      {...register(`screening_questions.${i}.q_type`)}
                    />
                    <div className="flex items-end pb-1">
                      <Controller
                        control={control}
                        name={`screening_questions.${i}.is_required`}
                        render={({ field }) => (
                          <Switch
                            id={`q-required-${i}`}
                            label={tf("questionRequired")}
                            checked={field.value}
                            disabled={isActive}
                            onCheckedChange={field.onChange}
                          />
                        )}
                      />
                    </div>
                  </div>
                  {showOptions && (
                    <Input
                      label={tf("questionOptions")}
                      help={tf("optionsHelp")}
                      disabled={isActive}
                      error={errors.screening_questions?.[i]?.options?.message}
                      {...register(`screening_questions.${i}.options`)}
                    />
                  )}
                </div>
              </li>
            );
          })}
        </ul>
        {!isActive && (
          <Button
            variant="secondary"
            size="sm"
            onClick={() =>
              append({
                question: "",
                q_type: "text",
                options: "",
                is_required: true,
              })
            }
          >
            <Plus aria-hidden weight="bold" className="size-4" />
            {tf("addQuestion")}
          </Button>
        )}
        <JdFieldIssueNote issues={qualityIssues} field="screening_questions" />
      </Fieldset>

      <div className="flex items-center justify-end gap-3 border-t border-[var(--border-default)] pt-5">
        {onCancel && (
          <Button variant="ghost" onClick={onCancel} disabled={mutation.isPending}>
            {tc("cancel")}
          </Button>
        )}
        <Button type="submit" variant="primary" loading={mutation.isPending}>
          <FloppyDisk aria-hidden weight="bold" className="size-4" />
          {mode === "create" ? t("createDraft") : tc("save")}
        </Button>
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
    </form>
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

function Fieldset({
  legend,
  description,
  children,
}: {
  legend: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <fieldset className="space-y-5 rounded-2xl border border-[var(--border-default)] bg-white/60 p-5 ">
      <div className="flex items-start gap-2.5 border-b border-[var(--border-default)] pb-4">
        <div className="mt-1 h-5 w-[3px] shrink-0 rounded-full bg-gradient-to-b from-[var(--brand-primary)] to-[var(--brand-teal)]" />
        <div>
          <legend className="text-sm font-bold tracking-tight text-[var(--text-primary)]">
            {legend}
          </legend>
          {description && (
            <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
              {description}
            </p>
          )}
        </div>
      </div>
      {children}
    </fieldset>
  );
}

function Textarea({
  id,
  label,
  rows = 4,
  required,
  error,
  register,
}: {
  id: string;
  label: string;
  rows?: number;
  required?: boolean;
  error?: string;
  register: UseFormRegisterReturn;
}) {
  const errorId = `${id}-error`;
  return (
    <div className="w-full">
      <label
        htmlFor={id}
        className="mb-1.5 block text-sm font-semibold text-[var(--text-primary)]"
      >
        {label}
        {required && (
          <span className="ml-0.5 text-[var(--brand-red)]" aria-hidden>
            *
          </span>
        )}
      </label>
      <textarea
        id={id}
        rows={rows}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        className="w-full resize-y rounded-xl border border-[var(--border-default)] bg-white px-3.5 py-2.5 text-sm text-[var(--text-primary)] outline-none transition-all hover:border-[var(--border-default)] focus:border-[var(--brand-primary)] focus:bg-white focus:ring-2 focus:ring-[var(--brand-primary)]/20"
        {...register}
      />
      {error && (
        <p id={errorId} className="mt-1 text-xs font-medium text-[var(--brand-red)]">
          {error}
        </p>
      )}
    </div>
  );
}
