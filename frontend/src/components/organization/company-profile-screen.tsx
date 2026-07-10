"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BadgeCheck,
  Building2,
  Clock3,
  FileCheck2,
  History,
  Info,
  Landmark,
  Lock,
  Send,
  UploadCloud,
} from "lucide-react";
import {
  Button,
  Input,
  Modal,
  Select,
  Textarea,
  useToast,
} from "@/components/ui";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  EmptyState,
  PageHeader,
  StatusChip,
  type ChipTone,
} from "@/components/kit";
import { CompanyLogoCard } from "@/components/organization/company-logo-card";
import {
  CompanyChangeDiff,
  CompanyDocumentList,
} from "@/components/organization/company-review-shared";
import {
  ApiError,
  companyProfileApi,
  organizationApi,
  COMPANY_DOC_KINDS,
  type CompanyDocKind,
  type CompanyProfile,
  type CompanyProfileUpdateBody,
} from "@/lib/api";
import { COMPANY_SIZES } from "@/lib/validation/organization";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { useAuthStore } from "@/stores/auth-store";
import { formatDateTime } from "@/lib/format";

const COSMETIC_KEYS = [
  "display_name",
  "website_url",
  "industry",
  "company_size",
  "founded_year",
  "headquarters_city",
  "headquarters_country",
  "description",
] as const;
const LEGAL_KEYS = ["legal_name", "tax_code", "registration_number"] as const;
type FormKey = (typeof COSMETIC_KEYS)[number] | (typeof LEGAL_KEYS)[number];
type FormState = Record<FormKey, string>;

const DOC_MAX_BYTES = 10 * 1024 * 1024;
const DOC_ACCEPT = "application/pdf,image/png,image/jpeg,image/webp";
const DOC_ALLOWED = new Set([
  "application/pdf",
  "image/png",
  "image/jpeg",
  "image/webp",
]);

const STATUS_CHIP: Record<string, ChipTone> = {
  pending: "warning",
  approved: "success",
  rejected: "danger",
  withdrawn: "neutral",
};

function toFormState(p: CompanyProfile): FormState {
  return {
    display_name: p.display_name ?? "",
    website_url: p.website_url ?? "",
    industry: p.industry ?? "",
    company_size: p.company_size ?? "",
    founded_year: p.founded_year != null ? String(p.founded_year) : "",
    headquarters_city: p.headquarters_city ?? "",
    headquarters_country: p.headquarters_country ?? "",
    description: p.description ?? "",
    legal_name: p.legal_name ?? "",
    tax_code: p.tax_code ?? "",
    registration_number: p.registration_number ?? "",
  };
}

/** Whether the caller may edit the profile (`organizations:update`). */
function canUpdateOrg(caps: {
  is_org_admin: boolean;
  grants: string[];
  by_resource: Record<string, string[]>;
} | undefined): boolean {
  if (!caps) return false;
  if (caps.is_org_admin) return true;
  if (caps.grants.includes("*:*")) return true;
  if (caps.grants.includes("organizations:update")) return true;
  const org = caps.by_resource.organizations ?? [];
  return org.includes("update") || org.includes("*");
}

export function CompanyProfileScreen() {
  const t = useTranslations("companyProfile");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");
  const locale = useLocale();
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const orgId = useAuthStore((s) => s.user?.orgId ?? null);

  const profileKey = React.useMemo(() => ["company-profile", orgId], [orgId]);

  const capsQuery = useQuery({
    queryKey: ["org", "my-capabilities"],
    queryFn: () => organizationApi.getMyCapabilities(),
    retry: false,
    staleTime: 60_000,
  });
  const canEdit = canUpdateOrg(capsQuery.data);

  const query = useQuery({
    queryKey: profileKey,
    queryFn: () => companyProfileApi.getProfile(orgId!),
    enabled: Boolean(orgId),
    retry: false,
  });
  const profile = query.data;

  const historyQuery = useQuery({
    queryKey: ["company-profile", orgId, "change-requests"],
    queryFn: () => companyProfileApi.listChangeRequests(orgId!),
    enabled: Boolean(orgId),
    retry: false,
    staleTime: 15_000,
  });

  // --- Editable form state (single source; baseline tracks server truth) --- //
  const [form, setForm] = React.useState<FormState | null>(null);
  const [baseline, setBaseline] = React.useState<FormState | null>(null);
  const [foundedError, setFoundedError] = React.useState<string | null>(null);
  const initedFor = React.useRef<string | null>(null);

  React.useEffect(() => {
    if (!profile) return;
    // Initialize once per profile id — don't clobber in-progress edits on refetch.
    if (initedFor.current === profile.id) return;
    initedFor.current = profile.id;
    const next = toFormState(profile);
    setForm(next);
    setBaseline(next);
  }, [profile]);

  const set = (key: FormKey, value: string) =>
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));

  const isDirty = (keys: readonly FormKey[]) =>
    Boolean(form && baseline && keys.some((k) => form[k].trim() !== baseline[k].trim()));

  function buildBody(keys: readonly FormKey[]): CompanyProfileUpdateBody {
    const body: CompanyProfileUpdateBody = {};
    if (!form || !baseline) return body;
    for (const k of keys) {
      const cur = form[k].trim();
      if (cur === baseline[k].trim()) continue;
      if (k === "founded_year") {
        body.founded_year = cur === "" ? null : Number(cur);
      } else if (k === "display_name") {
        if (cur !== "") body.display_name = cur; // required — never null
      } else {
        (body as Record<string, unknown>)[k] = cur === "" ? null : cur;
      }
    }
    return body;
  }

  function syncSaved(next: CompanyProfile, keys: readonly FormKey[]) {
    const nextForm = toFormState(next);
    setForm((prev) => {
      if (!prev) return prev;
      const merged = { ...prev };
      for (const k of keys) merged[k] = nextForm[k];
      return merged;
    });
    setBaseline((prev) => {
      const base = prev ?? nextForm;
      const merged = { ...base };
      for (const k of keys) merged[k] = nextForm[k];
      return merged;
    });
  }

  const handleConflict = React.useCallback(
    (e: unknown): boolean => {
      const reason = e instanceof ApiError && typeof e.details?.reason === "string" ? e.details.reason : undefined;
      if (reason === "version_conflict" || (e instanceof ApiError && e.isConflict)) {
        toast.show({ tone: "error", title: t("conflictToast"), description: t("conflictBody") });
        void query.refetch();
        return true;
      }
      return false;
    },
    [query, t, toast],
  );

  const saveCosmetic = useMutation({
    mutationFn: (body: CompanyProfileUpdateBody) =>
      companyProfileApi.updateProfile(orgId!, { ...body, version: profile?.version }),
    onSuccess: (result) => {
      qc.setQueryData(profileKey, result.profile);
      syncSaved(result.profile, COSMETIC_KEYS);
      toast.show({ tone: "success", title: t("savedToast") });
    },
    onError: (e) => {
      if (handleConflict(e)) return;
      toast.show({ tone: "error", title: getMessage(e) });
    },
  });

  const saveLegal = useMutation({
    mutationFn: (body: CompanyProfileUpdateBody) =>
      companyProfileApi.updateProfile(orgId!, { ...body, version: profile?.version }),
    onSuccess: (result) => {
      qc.setQueryData(profileKey, result.profile);
      // Live legal values are unchanged (approval-gated); reset inputs to them.
      syncSaved(result.profile, LEGAL_KEYS);
      void historyQuery.refetch();
      toast.show({
        tone: "success",
        title: result.requires_approval ? t("legal.submittedToast") : t("savedToast"),
      });
    },
    onError: (e) => {
      if (handleConflict(e)) return;
      toast.show({ tone: "error", title: getMessage(e) });
    },
  });

  const withdraw = useMutation({
    mutationFn: (reqId: string) => companyProfileApi.withdrawChangeRequest(orgId!, reqId),
    onSuccess: () => {
      void query.refetch();
      void historyQuery.refetch();
      toast.show({ tone: "success", title: t("pending.withdrawnToast") });
    },
    onError: (e) => {
      if (handleConflict(e)) return;
      toast.show({ tone: "error", title: getMessage(e) });
    },
  });

  const onSubmitCosmetic = () => {
    setFoundedError(null);
    const fy = form?.founded_year.trim() ?? "";
    if (fy !== "") {
      const n = Number(fy);
      if (!Number.isInteger(n) || n < 1800 || n > 2100) {
        setFoundedError(t("foundedError"));
        return;
      }
    }
    const body = buildBody(COSMETIC_KEYS);
    if (Object.keys(body).length === 0) {
      toast.show({ tone: "info", title: t("noChangesToast") });
      return;
    }
    saveCosmetic.mutate(body);
  };

  const onSubmitLegal = () => {
    const body = buildBody(LEGAL_KEYS);
    if (Object.keys(body).length === 0) {
      toast.show({ tone: "info", title: t("noChangesToast") });
      return;
    }
    saveLegal.mutate(body);
  };

  const refetchProfile = React.useCallback(() => {
    void query.refetch();
    void historyQuery.refetch();
  }, [query, historyQuery]);

  const [withdrawOpen, setWithdrawOpen] = React.useState(false);

  // ------------------------------- Errors -------------------------------- //
  const header = (
    <PageHeader
      title={t("title")}
      subtitle={t("subtitle")}
      actions={
        profile?.is_verified ? (
          <StatusChip tone="success" dot>
            <BadgeCheck aria-hidden className="size-3.5" strokeWidth={2} />
            {t("verified")}
          </StatusChip>
        ) : undefined
      }
    />
  );

  if (!orgId) {
    return (
      <>
        {header}
        <EmptyState kind="permission" title={tStates("permissionTitle")} description={t("permissionBody")} />
      </>
    );
  }

  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    return (
      <>
        {header}
        <EmptyState
          kind={err.isPermissionError ? "permission" : err.isAuthError ? "auth" : "error"}
          title={
            err.isPermissionError
              ? tStates("permissionTitle")
              : err.isAuthError
                ? tStates("authTitle")
                : tStates("errorTitle")
          }
          description={
            err.isPermissionError
              ? t("permissionBody")
              : err.isAuthError
                ? tStates("authBody")
                : tStates("errorBody")
          }
          action={
            !err.isPermissionError && !err.isAuthError ? (
              <Button variant="secondary" onClick={() => query.refetch()}>
                {tc("retry")}
              </Button>
            ) : undefined
          }
        />
      </>
    );
  }

  const pending = profile?.pending_change_request ?? null;
  const legalLocked = Boolean(pending) || !canEdit;
  const decided = (historyQuery.data ?? []).filter((r) => r.status !== "pending");

  return (
    <>
      {header}

      <div className="space-y-5">
        {!canEdit && !query.isPending && (
          <div className="flex items-center gap-2.5 rounded-xl border border-border bg-[var(--bg-subtle)] px-4 py-3 text-[0.8125rem] text-muted-foreground">
            <Info aria-hidden className="size-4 shrink-0" strokeWidth={1.8} />
            {t("readOnlyBanner")}
          </div>
        )}

        {/* Pending university review — surfaced prominently */}
        {pending && (
          <Card className="border-[var(--content-warning)]/30">
            <CardHeader>
              <div className="flex min-w-0 items-start gap-2.5">
                <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-[var(--content-warning-soft)]">
                  <Clock3 aria-hidden className="size-4 text-[var(--content-warning)]" strokeWidth={1.9} />
                </span>
                <div className="min-w-0">
                  <CardTitle>{t("pending.title")}</CardTitle>
                  <CardDescription>
                    {pending.created_at
                      ? t("pending.submittedAt", { date: formatDateTime(pending.created_at, locale) })
                      : t("pending.body")}
                  </CardDescription>
                </div>
              </div>
              <StatusChip tone="warning" dot>
                {pending.status_label}
              </StatusChip>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <p className="mb-2 type-caption font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                  {t("pending.changesTitle")}
                </p>
                <CompanyChangeDiff
                  changes={pending.changes}
                  emptyValueLabel={t("valueEmpty")}
                  emptyLabel={t("pending.noChanges")}
                />
              </div>
              {pending.documents.length > 0 && (
                <div>
                  <p className="mb-2 type-caption font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                    {t("pending.docsTitle")}
                  </p>
                  <CompanyDocumentList
                    documents={pending.documents}
                    emptyLabel={t("docs.pendingEmpty")}
                    viewLabel={t("docs.view")}
                  />
                </div>
              )}
              {canEdit && (
                <div className="flex justify-end">
                  <Button variant="ghost" size="sm" onClick={() => setWithdrawOpen(true)}>
                    {t("pending.withdraw")}
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Logo + identity */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Building2 aria-hidden className="size-4 text-muted-foreground" strokeWidth={1.8} />
              <CardTitle>{t("logoTitle")}</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            {profile ? (
              <CompanyLogoCard
                orgId={profile.id}
                displayName={profile.display_name}
                logoUrl={profile.logo_url}
                version={profile.version}
                disabled={!canEdit}
                onChanged={refetchProfile}
              />
            ) : (
              <div className="h-16 animate-skeleton rounded-lg bg-[var(--bg-muted)]" />
            )}
          </CardContent>
        </Card>

        {/* Public (cosmetic) info — immediate */}
        <Card>
          <CardHeader>
            <div>
              <CardTitle>{t("public.title")}</CardTitle>
              <CardDescription>{t("public.intro")}</CardDescription>
            </div>
            <StatusChip tone="info">{t("public.immediateHint")}</StatusChip>
          </CardHeader>
          <CardContent>
            {query.isPending || !form ? (
              <FormSkeleton />
            ) : (
              <form
                className="space-y-5"
                onSubmit={(e) => {
                  e.preventDefault();
                  onSubmitCosmetic();
                }}
                noValidate
              >
                <Input
                  label={t("companyName")}
                  required
                  disabled={!canEdit}
                  value={form.display_name}
                  onChange={(e) => set("display_name", e.target.value)}
                />
                <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                  <Input
                    type="url"
                    label={t("website")}
                    placeholder="https://"
                    disabled={!canEdit}
                    value={form.website_url}
                    onChange={(e) => set("website_url", e.target.value)}
                  />
                  <Input
                    label={t("industry")}
                    disabled={!canEdit}
                    value={form.industry}
                    onChange={(e) => set("industry", e.target.value)}
                  />
                  <Select
                    label={t("companySize")}
                    disabled={!canEdit}
                    value={form.company_size}
                    onChange={(e) => set("company_size", e.target.value)}
                    options={[
                      { value: "", label: t("selectPlaceholder") },
                      ...COMPANY_SIZES.map((s) => ({ value: s, label: s })),
                    ]}
                  />
                  <Input
                    label={t("founded")}
                    inputMode="numeric"
                    placeholder="2015"
                    disabled={!canEdit}
                    error={foundedError ?? undefined}
                    value={form.founded_year}
                    onChange={(e) => set("founded_year", e.target.value)}
                  />
                  <Input
                    label={t("city")}
                    disabled={!canEdit}
                    value={form.headquarters_city}
                    onChange={(e) => set("headquarters_city", e.target.value)}
                  />
                  <Input
                    label={t("country")}
                    disabled={!canEdit}
                    value={form.headquarters_country}
                    onChange={(e) => set("headquarters_country", e.target.value)}
                  />
                </div>
                <Textarea
                  label={t("description")}
                  rows={4}
                  disabled={!canEdit}
                  value={form.description}
                  onChange={(e) => set("description", e.target.value)}
                />
                <div className="flex items-center justify-between gap-3">
                  <p className="flex items-center gap-1.5 type-caption text-muted-foreground">
                    <Building2 aria-hidden className="size-3.5" strokeWidth={1.8} />
                    {t("slugNote", { slug: profile?.slug ?? "" })}
                  </p>
                  {canEdit && (
                    <Button
                      type="submit"
                      variant="primary"
                      loading={saveCosmetic.isPending}
                      disabled={!isDirty(COSMETIC_KEYS)}
                    >
                      {tc("save")}
                    </Button>
                  )}
                </div>
              </form>
            )}
          </CardContent>
        </Card>

        {/* Legal identity — approval-gated */}
        <Card>
          <CardHeader>
            <div className="flex min-w-0 items-start gap-2.5">
              <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-[var(--viz-indigo-soft)]">
                <Landmark aria-hidden className="size-4 text-[var(--viz-indigo)]" strokeWidth={1.8} />
              </span>
              <div className="min-w-0">
                <CardTitle>{t("legal.title")}</CardTitle>
                <CardDescription>{t("legal.reviewHint")}</CardDescription>
              </div>
            </div>
            <StatusChip tone="warning">{t("legal.gated")}</StatusChip>
          </CardHeader>
          <CardContent>
            {query.isPending || !form ? (
              <FormSkeleton rows={3} />
            ) : (
              <form
                className="space-y-5"
                onSubmit={(e) => {
                  e.preventDefault();
                  onSubmitLegal();
                }}
                noValidate
              >
                {pending && (
                  <div className="flex items-start gap-2.5 rounded-lg border border-[var(--content-warning)]/30 bg-[var(--content-warning-soft)] px-3.5 py-2.5">
                    <Lock aria-hidden className="mt-0.5 size-4 shrink-0 text-[var(--content-warning)]" strokeWidth={1.8} />
                    <div className="min-w-0">
                      <p className="text-[0.8125rem] font-semibold text-foreground">{t("legal.lockedTitle")}</p>
                      <p className="type-caption text-muted-foreground">{t("legal.lockedBody")}</p>
                    </div>
                  </div>
                )}
                <Input
                  label={t("legal.legalName")}
                  disabled={legalLocked}
                  value={form.legal_name}
                  onChange={(e) => set("legal_name", e.target.value)}
                />
                <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                  <Input
                    label={t("legal.taxCode")}
                    disabled={legalLocked}
                    value={form.tax_code}
                    onChange={(e) => set("tax_code", e.target.value)}
                  />
                  <Input
                    label={t("legal.regNumber")}
                    disabled={legalLocked}
                    value={form.registration_number}
                    onChange={(e) => set("registration_number", e.target.value)}
                  />
                </div>
                {canEdit && !pending && (
                  <div className="flex justify-end">
                    <Button
                      type="submit"
                      variant="primary"
                      loading={saveLegal.isPending}
                      disabled={!isDirty(LEGAL_KEYS)}
                    >
                      <Send aria-hidden className="size-4" strokeWidth={1.8} />
                      {t("legal.submit")}
                    </Button>
                  </div>
                )}
              </form>
            )}
          </CardContent>
        </Card>

        {/* Verification documents */}
        <Card>
          <CardHeader>
            <div className="flex min-w-0 items-start gap-2.5">
              <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-[var(--viz-sky-soft)]">
                <FileCheck2 aria-hidden className="size-4 text-[var(--viz-sky)]" strokeWidth={1.8} />
              </span>
              <div className="min-w-0">
                <CardTitle>{t("docs.title")}</CardTitle>
                <CardDescription>{t("docs.intro")}</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-5">
            <div>
              <p className="mb-2 type-caption font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                {t("docs.approvedTitle")}
              </p>
              <CompanyDocumentList
                documents={profile?.verification_documents ?? []}
                emptyLabel={t("docs.empty")}
                viewLabel={t("docs.view")}
              />
            </div>
            {pending && pending.documents.length > 0 && (
              <div>
                <p className="mb-2 flex items-center gap-1.5 type-caption font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                  <Clock3 aria-hidden className="size-3.5 text-[var(--content-warning)]" strokeWidth={1.8} />
                  {t("docs.pendingTitle")}
                </p>
                <CompanyDocumentList
                  documents={pending.documents}
                  emptyLabel={t("docs.pendingEmpty")}
                  viewLabel={t("docs.view")}
                />
              </div>
            )}
            {canEdit && profile && (
              <DocumentUpload orgId={profile.id} onUploaded={refetchProfile} />
            )}
          </CardContent>
        </Card>

        {/* Request history */}
        {decided.length > 0 && (
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <History aria-hidden className="size-4 text-muted-foreground" strokeWidth={1.8} />
                <CardTitle>{t("history.title")}</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <ul className="space-y-3">
                {decided.slice(0, 5).map((req) => (
                  <li key={req.id} className="rounded-lg border border-border bg-[var(--bg-subtle)] px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <StatusChip tone={STATUS_CHIP[req.status] ?? "neutral"} dot>
                        {req.status_label}
                      </StatusChip>
                      {req.decided_at && (
                        <span className="type-caption text-muted-foreground">
                          {t("history.decidedAt", { date: formatDateTime(req.decided_at, locale) })}
                        </span>
                      )}
                    </div>
                    {req.changes.length > 0 && (
                      <p className="mt-2 type-caption text-muted-foreground">
                        {req.changes.map((c) => c.label).join(" · ")}
                      </p>
                    )}
                    {req.review_note && (
                      <div className="mt-2 rounded-md bg-[var(--bg-muted)] px-3 py-2">
                        <p className="type-caption font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                          {t("history.reviewNote")}
                        </p>
                        <p className="mt-0.5 text-[0.8125rem] text-foreground">{req.review_note}</p>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Withdraw confirm */}
      <Modal
        open={withdrawOpen}
        onClose={() => setWithdrawOpen(false)}
        title={t("pending.withdrawConfirmTitle")}
        description={t("pending.withdrawConfirmBody")}
        size="sm"
        footer={
          <>
            <Button variant="ghost" disabled={withdraw.isPending} onClick={() => setWithdrawOpen(false)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="danger"
              loading={withdraw.isPending}
              onClick={() => {
                if (pending) withdraw.mutate(pending.id, { onSettled: () => setWithdrawOpen(false) });
              }}
            >
              {t("pending.withdrawConfirm")}
            </Button>
          </>
        }
      >
        <p className="type-small text-muted-foreground">{t("pending.withdrawConfirmBody")}</p>
      </Modal>
    </>
  );
}

/* ----------------------------- Sub-components ---------------------------- */

function FormSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-4">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-10 w-full animate-skeleton rounded-lg bg-[var(--bg-muted)]" />
      ))}
    </div>
  );
}

/** Verification-document uploader — always awaits university approval. */
function DocumentUpload({ orgId, onUploaded }: { orgId: string; onUploaded: () => void }) {
  const t = useTranslations("companyProfile");
  const toast = useToast();
  const getMessage = useApiErrorMessage();
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [kind, setKind] = React.useState<CompanyDocKind>("business_license");
  const [file, setFile] = React.useState<File | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const upload = useMutation({
    mutationFn: (f: File) => companyProfileApi.uploadDocument(orgId, f, kind),
    onSuccess: () => {
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      toast.show({ tone: "success", title: t("docs.uploadedToast") });
      onUploaded();
    },
    onError: (e) => {
      const reason = e instanceof ApiError && typeof e.details?.reason === "string" ? e.details.reason : undefined;
      if (reason === "file_too_large") setError(t("docs.errTooLarge"));
      else if (reason === "unsupported_type") setError(t("docs.errUnsupported"));
      else if (reason === "empty_file") setError(t("docs.errEmpty"));
      else setError(getMessage(e));
    },
  });

  function onSelect(e: React.ChangeEvent<HTMLInputElement>) {
    setError(null);
    const f = e.target.files?.[0] ?? null;
    if (!f) {
      setFile(null);
      return;
    }
    if (!DOC_ALLOWED.has(f.type)) {
      setError(t("docs.errUnsupported"));
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }
    if (f.size > DOC_MAX_BYTES) {
      setError(t("docs.errTooLarge"));
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }
    if (f.size === 0) {
      setError(t("docs.errEmpty"));
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }
    setFile(f);
  }

  return (
    <div className="rounded-xl border border-dashed border-border bg-[var(--bg-subtle)] p-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Select
          label={t("docs.kindLabel")}
          value={kind}
          onChange={(e) => setKind(e.target.value as CompanyDocKind)}
          options={COMPANY_DOC_KINDS.map((k) => ({ value: k, label: t(`docs.kind.${k}` as never) }))}
        />
        <div>
          <label htmlFor="doc-file" className="mb-1.5 block text-[0.8125rem] font-medium text-foreground">
            {t("docs.fileLabel")}
          </label>
          <input
            ref={inputRef}
            id="doc-file"
            type="file"
            accept={DOC_ACCEPT}
            onChange={onSelect}
            aria-describedby="doc-hint"
            disabled={upload.isPending}
            className="block w-full cursor-pointer text-sm text-muted-foreground file:mr-4 file:cursor-pointer file:rounded-lg file:border-0 file:bg-[var(--bg-muted)] file:px-4 file:py-2 file:text-sm file:font-semibold file:text-foreground disabled:cursor-not-allowed disabled:opacity-60"
          />
        </div>
      </div>
      <p id="doc-hint" className="mt-2 type-caption text-muted-foreground">
        {t("docs.fileHint")}
      </p>
      {error && (
        <p role="alert" className="mt-2 text-[0.8125rem] font-medium text-[var(--content-danger)]">
          {error}
        </p>
      )}
      <div className="mt-3 flex justify-end">
        <Button
          type="button"
          variant="secondary"
          size="sm"
          loading={upload.isPending}
          disabled={!file}
          onClick={() => file && upload.mutate(file)}
        >
          <UploadCloud aria-hidden className="size-4" strokeWidth={1.9} />
          {t("docs.upload")}
        </Button>
      </div>
    </div>
  );
}
