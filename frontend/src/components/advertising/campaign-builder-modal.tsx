"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Info, Megaphone, Target } from "lucide-react";
import {
  Button,
  Input,
  Modal,
  Select,
  SponsoredLabel,
  Textarea,
  useToast,
} from "@/components/ui";
import {
  ApiError,
  advertisingApi,
  AD_SURFACES,
  CAMPAIGN_OBJECTIVES,
  CAMPAIGN_PACINGS,
  COARSE_CAREERS,
  COARSE_LOCATIONS,
  COARSE_MAJORS,
  COARSE_WORK_MODES,
  COARSE_YEAR_COHORTS,
  type AdCampaign,
  type CampaignCreateBody,
  type CampaignObjective,
  type CampaignPacing,
  type CampaignTargeting,
  type AdSurface,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { useCampaignLabels } from "@/lib/advertising/campaign-labels";
import { useReachSummary } from "@/lib/advertising/use-reach-summary";
import { TokenMultiSelect } from "./token-multi-select";

/** Today as a date-input value (yyyy-mm-dd). */
function todayInput(): string {
  return new Date().toISOString().slice(0, 10);
}
function plusDays(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}
function toStartIso(date: string): string {
  return new Date(`${date}T00:00:00`).toISOString();
}
function toEndIso(date: string): string {
  return new Date(`${date}T23:59:59`).toISOString();
}

/**
 * Create / edit an allocation-engine campaign (spec §7.0). Purpose-built form:
 * name + objective + surface + budget + pacing + schedule + COARSE targeting
 * (allowlist chips, never a GPS/exact-location box) + creative, with a
 * plain-language reach summary and the MANDATORY non-removable disclosure
 * acknowledgement before submit. "Save draft" persists without submitting.
 *
 * Note: the per-impression delivery rate (CPM) is set by VinUni server-side and
 * is intentionally NOT an advertiser input — the budget caps total spend.
 */
export function CampaignBuilderModal({
  open,
  onClose,
  campaign,
}: {
  open: boolean;
  onClose: () => void;
  /** When set, edit this draft/rejected campaign; otherwise create new. */
  campaign?: AdCampaign | null;
}) {
  const t = useTranslations("advertising.campaign");
  const tc = useTranslations("common");
  const sponsoredTag = useTranslations("advertising")("sponsoredTag");
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();
  const labels = useCampaignLabels();
  const reachSummary = useReachSummary();
  const isEdit = !!campaign;

  const [name, setName] = React.useState("");
  const [objective, setObjective] = React.useState<CampaignObjective>("awareness");
  const [surface, setSurface] = React.useState<AdSurface>("discovery_feed");
  const [budget, setBudget] = React.useState("");
  const [pacing, setPacing] = React.useState<CampaignPacing>("even");
  const [start, setStart] = React.useState(todayInput());
  const [end, setEnd] = React.useState(plusDays(14));
  const [targeting, setTargeting] = React.useState<CampaignTargeting>({});
  const [headline, setHeadline] = React.useState("");
  const [body, setBody] = React.useState("");
  const [imageRef, setImageRef] = React.useState("");
  const [clickTarget, setClickTarget] = React.useState("");
  const [altVi, setAltVi] = React.useState("");
  const [altEn, setAltEn] = React.useState("");
  const [disclosure, setDisclosure] = React.useState(false);
  const [fieldError, setFieldError] = React.useState<string | null>(null);
  const [disclosureError, setDisclosureError] = React.useState<string | null>(null);

  /* Reset / prefill on open. */
  React.useEffect(() => {
    if (!open) return;
    setFieldError(null);
    setDisclosureError(null);
    if (campaign) {
      setName(campaign.name);
      setObjective((campaign.objective as CampaignObjective) ?? "awareness");
      setSurface((campaign.surface as AdSurface) ?? "discovery_feed");
      setBudget(campaign.budget_amount ? String(Math.round(Number(campaign.budget_amount))) : "");
      setPacing((campaign.pacing as CampaignPacing) ?? "even");
      setStart((campaign.start_at ?? new Date().toISOString()).slice(0, 10));
      setEnd((campaign.end_at ?? plusDays(14)).slice(0, 10));
      setTargeting(campaign.targeting ?? {});
      setHeadline(campaign.creative?.headline ?? "");
      setBody(campaign.creative?.body ?? "");
      setImageRef(campaign.creative?.image_ref ?? "");
      setClickTarget(campaign.creative?.click_target ?? "");
      setAltVi(campaign.creative?.alt_vi ?? "");
      setAltEn(campaign.creative?.alt_en ?? "");
      setDisclosure(campaign.disclosure_confirmed);
    } else {
      setName("");
      setObjective("awareness");
      setSurface("discovery_feed");
      setBudget("");
      setPacing("even");
      setStart(todayInput());
      setEnd(plusDays(14));
      setTargeting({});
      setHeadline("");
      setBody("");
      setImageRef("");
      setClickTarget("");
      setAltVi("");
      setAltEn("");
      setDisclosure(false);
    }
  }, [open, campaign]);

  const opts = (values: readonly string[], group: "location" | "major" | "career" | "workMode" | "yearCohort") =>
    values.map((v) => ({ value: v, label: labels[group](v) }));

  function validate(): CampaignCreateBody | null {
    if (!name.trim()) {
      setFieldError(t("form.nameRequired"));
      return null;
    }
    const budgetNum = Number(budget);
    if (!budget.trim() || Number.isNaN(budgetNum) || budgetNum <= 0) {
      setFieldError(t("form.budgetRequired"));
      return null;
    }
    if (!start || !end) {
      setFieldError(t("form.scheduleRequired"));
      return null;
    }
    if (new Date(end).getTime() <= new Date(start).getTime()) {
      setFieldError(t("form.scheduleOrder"));
      return null;
    }
    setFieldError(null);
    const cleanTargeting: CampaignTargeting = {};
    if (targeting.locations?.length) cleanTargeting.locations = targeting.locations;
    if (targeting.majors?.length) cleanTargeting.majors = targeting.majors;
    if (targeting.careers?.length) cleanTargeting.careers = targeting.careers;
    if (targeting.work_modes?.length) cleanTargeting.work_modes = targeting.work_modes;
    if (targeting.year_cohorts?.length) cleanTargeting.year_cohorts = targeting.year_cohorts;
    return {
      name: name.trim(),
      objective,
      surface,
      budget_amount: budgetNum,
      pacing,
      start_at: toStartIso(start),
      end_at: toEndIso(end),
      targeting: cleanTargeting,
      creative: {
        headline: headline.trim() || null,
        body: body.trim() || null,
        image_ref: imageRef.trim() || null,
        click_target: clickTarget.trim() || null,
        alt_vi: altVi.trim() || null,
        alt_en: altEn.trim() || null,
      },
    };
  }

  function handleError(e: unknown) {
    const details = e instanceof ApiError ? (e.details ?? {}) : {};
    const reason = typeof details.reason === "string" ? details.reason : undefined;
    if (reason === "disclosure_required") {
      setDisclosureError(t("errors.disclosureRequired"));
      return;
    }
    if (reason === "forbidden_targeting" || reason === "unknown_targeting") {
      setFieldError(t("errors.targetingForbidden"));
      return;
    }
    if (typeof details.field === "string" && details.field === "budget_amount") {
      setFieldError(t("errors.budgetInvalid"));
      return;
    }
    if (typeof details.field === "string") {
      setFieldError(getMessage(e));
      return;
    }
    if (reason === "active_campaign_limit") {
      toast.show({ tone: "error", title: t("errors.limitTitle"), description: t("errors.limitBody") });
      return;
    }
    if (reason === "version_conflict" || (e instanceof ApiError && e.isConflict)) {
      toast.show({ tone: "error", title: t("errors.conflictTitle"), description: t("errors.conflictBody") });
      void qc.invalidateQueries({ queryKey: ["advertising", "campaigns"] });
      onClose();
      return;
    }
    toast.show({ tone: "error", title: getMessage(e) });
  }

  const save = useMutation({
    mutationFn: async ({ payload, submit }: { payload: CampaignCreateBody; submit: boolean }) => {
      let saved: AdCampaign;
      if (campaign) {
        saved = await advertisingApi.updateCampaign(campaign.id, {
          ...payload,
          disclosure_confirmed: submit ? true : disclosure,
          version: campaign.version,
        });
      } else {
        saved = await advertisingApi.createCampaign({
          ...payload,
          disclosure_confirmed: disclosure,
        });
      }
      if (submit) {
        saved = await advertisingApi.submitCampaign(saved.id, {
          disclosure_confirmed: true,
          version: saved.version,
        });
      }
      return saved;
    },
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ["advertising", "campaigns"] });
      toast.show({
        tone: "success",
        title: vars.submit ? t("toast.submitted") : isEdit ? t("toast.updated") : t("toast.created"),
      });
      onClose();
    },
    onError: handleError,
  });

  function onSaveDraft() {
    const payload = validate();
    if (!payload) return;
    save.mutate({ payload, submit: false });
  }

  function onSubmit() {
    if (!disclosure) {
      setDisclosureError(t("form.disclosureRequired"));
      return;
    }
    setDisclosureError(null);
    const payload = validate();
    if (!payload) return;
    save.mutate({ payload, submit: true });
  }

  const previewReach = reachSummary(targeting);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isEdit ? t("form.editTitle") : t("form.createTitle")}
      description={t("form.subtitle")}
      size="lg"
      closeLabel={tc("close")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={save.isPending}>
            {tc("cancel")}
          </Button>
          <Button
            variant="secondary"
            loading={save.isPending && save.variables?.submit === false}
            disabled={save.isPending}
            onClick={onSaveDraft}
          >
            {t("form.saveDraft")}
          </Button>
          <Button
            variant="primary"
            loading={save.isPending && save.variables?.submit === true}
            disabled={save.isPending || !disclosure}
            onClick={onSubmit}
          >
            <Megaphone aria-hidden className="size-4" strokeWidth={2} />
            {t("form.submit")}
          </Button>
        </>
      }
    >
      <div className="space-y-6">
        {/* Basics */}
        <section className="space-y-4">
          <SectionLabel>{t("form.stepBasics")}</SectionLabel>
          <Input
            label={t("form.nameLabel")}
            required
            value={name}
            placeholder={t("form.namePlaceholder")}
            onChange={(e) => {
              setName(e.target.value);
              setFieldError(null);
            }}
          />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Select
              label={t("form.objectiveLabel")}
              required
              value={objective}
              onChange={(e) => setObjective(e.target.value as CampaignObjective)}
              options={CAMPAIGN_OBJECTIVES.map((o) => ({ value: o, label: labels.objective(o) }))}
            />
            <Select
              label={t("form.surfaceLabel")}
              required
              value={surface}
              onChange={(e) => setSurface(e.target.value as AdSurface)}
              options={AD_SURFACES.map((s) => ({ value: s, label: labels.surface(s) }))}
              help={t("form.surfaceHint")}
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              type="number"
              inputMode="numeric"
              min={0}
              step={100000}
              label={t("form.budgetLabel")}
              required
              value={budget}
              onChange={(e) => {
                setBudget(e.target.value);
                setFieldError(null);
              }}
              help={t("form.budgetHint")}
            />
            <Select
              label={t("form.pacingLabel")}
              value={pacing}
              onChange={(e) => setPacing(e.target.value as CampaignPacing)}
              options={CAMPAIGN_PACINGS.map((p) => ({ value: p, label: labels.pacing(p) }))}
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              type="date"
              label={t("form.startLabel")}
              required
              min={todayInput()}
              value={start}
              onChange={(e) => {
                setStart(e.target.value);
                setFieldError(null);
              }}
            />
            <Input
              type="date"
              label={t("form.endLabel")}
              required
              min={start}
              value={end}
              onChange={(e) => {
                setEnd(e.target.value);
                setFieldError(null);
              }}
            />
          </div>
        </section>

        {/* Targeting (coarse only) */}
        <section className="space-y-4">
          <SectionLabel>{t("form.stepTargeting")}</SectionLabel>
          <p className="flex items-start gap-2 rounded-lg border border-border px-3 py-2 type-caption text-muted-foreground">
            <Target aria-hidden className="mt-0.5 size-3.5 shrink-0" strokeWidth={1.9} />
            {t("form.targetingHint")}
          </p>
          <TokenMultiSelect
            label={t("form.targetLocations")}
            options={opts(COARSE_LOCATIONS, "location")}
            value={targeting.locations ?? []}
            onChange={(v) => setTargeting((prev) => ({ ...prev, locations: v }))}
          />
          <TokenMultiSelect
            label={t("form.targetMajors")}
            options={opts(COARSE_MAJORS, "major")}
            value={targeting.majors ?? []}
            onChange={(v) => setTargeting((prev) => ({ ...prev, majors: v }))}
          />
          <TokenMultiSelect
            label={t("form.targetCareers")}
            options={opts(COARSE_CAREERS, "career")}
            value={targeting.careers ?? []}
            onChange={(v) => setTargeting((prev) => ({ ...prev, careers: v }))}
          />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <TokenMultiSelect
              label={t("form.targetWorkModes")}
              options={opts(COARSE_WORK_MODES, "workMode")}
              value={targeting.work_modes ?? []}
              onChange={(v) => setTargeting((prev) => ({ ...prev, work_modes: v }))}
            />
            <TokenMultiSelect
              label={t("form.targetYearCohorts")}
              options={opts(COARSE_YEAR_COHORTS, "yearCohort")}
              value={targeting.year_cohorts ?? []}
              onChange={(v) => setTargeting((prev) => ({ ...prev, year_cohorts: v }))}
            />
          </div>
          {/* Plain-language reach summary */}
          <div
            className="rounded-xl border border-border px-3.5 py-3"
            style={{ background: "var(--content-info-soft, var(--bg-subtle))" }}
          >
            <p className="type-caption font-semibold uppercase tracking-wide text-muted-foreground">
              {t("form.reachPreview")}
            </p>
            <p className="mt-1 type-small text-foreground">{previewReach}</p>
          </div>
        </section>

        {/* Creative */}
        <section className="space-y-4">
          <SectionLabel>{t("form.stepCreative")}</SectionLabel>
          <p className="type-caption text-muted-foreground">{t("form.creativeHint")}</p>
          <Input
            label={t("form.headlineLabel")}
            value={headline}
            placeholder={t("form.headlinePlaceholder")}
            onChange={(e) => setHeadline(e.target.value)}
          />
          <Textarea
            label={t("form.bodyLabel")}
            rows={2}
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label={t("form.imageLabel")}
              value={imageRef}
              onChange={(e) => setImageRef(e.target.value)}
              help={t("form.imageHint")}
            />
            <Input
              label={t("form.clickTargetLabel")}
              value={clickTarget}
              onChange={(e) => setClickTarget(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input label={t("form.altViLabel")} value={altVi} onChange={(e) => setAltVi(e.target.value)} />
            <Input label={t("form.altEnLabel")} value={altEn} onChange={(e) => setAltEn(e.target.value)} />
          </div>
        </section>

        {fieldError && (
          <p className="type-small font-medium text-[var(--content-danger)]" role="alert">
            {fieldError}
          </p>
        )}

        {/* Mandatory non-removable disclosure acknowledgement */}
        <div
          className="rounded-xl border px-3.5 py-3"
          style={{
            borderColor: disclosureError ? "var(--content-danger)" : "var(--border-default)",
            background: disclosureError ? "var(--content-danger-soft)" : "var(--content-warning-soft)",
          }}
        >
          <label className="flex items-start gap-2.5 text-sm">
            <input
              type="checkbox"
              checked={disclosure}
              required
              aria-required="true"
              aria-invalid={disclosureError ? true : undefined}
              aria-describedby="campaign-disclosure-desc"
              onChange={(e) => {
                setDisclosure(e.target.checked);
                if (e.target.checked) setDisclosureError(null);
              }}
              className="mt-0.5 size-4 shrink-0 rounded border-[var(--border-default)] text-[var(--brand-primary)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
            />
            <span id="campaign-disclosure-desc" className="min-w-0 text-foreground">
              <span className="inline-flex flex-wrap items-center gap-1.5 font-semibold">
                <Info aria-hidden className="size-4 shrink-0" strokeWidth={1.9} style={{ color: "var(--content-warning)" }} />
                {t("form.disclosureLabel")}
                <SponsoredLabel label={sponsoredTag} />
              </span>
              <span className="mt-0.5 block type-caption text-muted-foreground">
                {t("form.disclosureHelp")}
              </span>
            </span>
          </label>
          {disclosureError && (
            <p className="mt-1.5 type-caption font-medium" style={{ color: "var(--content-danger)" }} role="alert">
              {disclosureError}
            </p>
          )}
        </div>
      </div>
    </Modal>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="type-caption font-semibold uppercase tracking-[0.08em] text-muted-foreground">
      {children}
    </h3>
  );
}
