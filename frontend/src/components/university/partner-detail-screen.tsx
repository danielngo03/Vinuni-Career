"use client";

import { useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Buildings,
  ShieldWarning,
  SignIn,
  Flag,
  NotePencil,
  ChartLineUp,
  UserCircle,
  CheckCircle,
  Plus,
} from "@phosphor-icons/react";
import {
  Button,
  DataTable,
  EmptyState,
  Modal,
  Select,
  Skeleton,
  StatusBadge,
  Tabs,
  TabPanel,
  Textarea,
  useToast,
  type Column,
  type StatusTone,
  type TabItem,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { SectionCard } from "@/components/settings/section-card";
import {
  ApiError,
  organizationApi,
  partnerApi,
  type OrgRiskFlag,
  type OrgNote,
  type RiskFlagSeverity,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { formatDateTime } from "@/lib/format";

const TABS_ID = "partner-detail";

const SEVERITY_TONE: Record<RiskFlagSeverity, StatusTone> = {
  low: "info",
  medium: "pending",
  high: "rejected",
};

const SEVERITY_LABEL_KEY: Record<RiskFlagSeverity, string> = {
  low: "riskFlags.severityLow",
  medium: "riskFlags.severityMedium",
  high: "riskFlags.severityHigh",
};

export function PartnerDetailScreen({ orgId }: { orgId: string }) {
  const t = useTranslations("partnersDetail");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const [tab, setTab] = useState("overview");
  const [ownerDraft, setOwnerDraft] = useState<string>("");
  const [ownerEditing, setOwnerEditing] = useState(false);
  const [raiseOpen, setRaiseOpen] = useState(false);
  const [flagType, setFlagType] = useState("");
  const [flagSeverity, setFlagSeverity] = useState<RiskFlagSeverity>("medium");
  const [flagNote, setFlagNote] = useState("");
  const [resolving, setResolving] = useState<OrgRiskFlag | null>(null);
  const [resolutionNote, setResolutionNote] = useState("");
  const [noteDraft, setNoteDraft] = useState("");
  const [noteError, setNoteError] = useState<string | null>(null);

  // Company display name: best-effort from the registration list (CRM detail
  // has no dedicated "get org by id" read for an arbitrary partner org).
  const registrationsQuery = useQuery({
    queryKey: ["admin", "partners", "all"],
    queryFn: () => partnerApi.listRegistrations(),
    retry: false,
    staleTime: 30_000,
  });
  const registration = registrationsQuery.data?.find((r) => r.created_org_id === orgId);

  const qualityQuery = useQuery({
    queryKey: ["org", orgId, "profile-quality"],
    queryFn: () => organizationApi.getProfileQuality(orgId),
    retry: false,
  });
  const seatsQuery = useQuery({
    queryKey: ["org", orgId, "recruiter-seats"],
    queryFn: () => organizationApi.getRecruiterSeats(orgId),
    retry: false,
  });
  const campusOwnerQuery = useQuery({
    queryKey: ["org", orgId, "campus-owner"],
    queryFn: () => organizationApi.getCampusOwner(orgId),
    retry: false,
  });
  // University staff directory (own org's members) for the owner picker.
  const staffQuery = useQuery({
    queryKey: ["org", "members"],
    queryFn: () => organizationApi.listMembers(),
    retry: false,
    enabled: ownerEditing,
  });
  const riskFlagsQuery = useQuery({
    queryKey: ["org", orgId, "risk-flags"],
    queryFn: () => organizationApi.listRiskFlags(orgId),
    retry: false,
  });
  const notesQuery = useQuery({
    queryKey: ["org", orgId, "notes"],
    queryFn: () => organizationApi.listNotes(orgId),
    retry: false,
  });
  const activityQuery = useQuery({
    queryKey: ["org", orgId, "crm", "activity"],
    queryFn: () => organizationApi.getCrmActivity(orgId),
    retry: false,
  });
  const hiringQuery = useQuery({
    queryKey: ["org", orgId, "crm", "hiring-outcomes"],
    queryFn: () => organizationApi.getHiringOutcomes(orgId),
    retry: false,
  });

  const setOwner = useMutation({
    mutationFn: (ownerUserId: string | null) =>
      organizationApi.setCampusOwner(orgId, ownerUserId),
    onSuccess: () => {
      setOwnerEditing(false);
      toast.show({ tone: "success", title: t("campusOwner.savedToast") });
      void qc.invalidateQueries({ queryKey: ["org", orgId, "campus-owner"] });
    },
    onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
  });

  const raiseFlag = useMutation({
    mutationFn: () =>
      organizationApi.raiseRiskFlag(orgId, {
        flag_type: flagType.trim(),
        severity: flagSeverity,
        note: flagNote.trim() || null,
      }),
    onSuccess: () => {
      setRaiseOpen(false);
      setFlagType("");
      setFlagSeverity("medium");
      setFlagNote("");
      toast.show({ tone: "success", title: t("riskFlags.raisedToast") });
      void qc.invalidateQueries({ queryKey: ["org", orgId, "risk-flags"] });
    },
    onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
  });

  const resolveFlag = useMutation({
    mutationFn: (flag: OrgRiskFlag) =>
      organizationApi.resolveRiskFlag(orgId, flag.id, resolutionNote.trim() || null),
    onSuccess: () => {
      setResolving(null);
      setResolutionNote("");
      toast.show({ tone: "success", title: t("riskFlags.resolvedToast") });
      void qc.invalidateQueries({ queryKey: ["org", orgId, "risk-flags"] });
    },
    onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
  });

  const addNote = useMutation({
    mutationFn: () => organizationApi.createNote(orgId, noteDraft.trim()),
    onSuccess: () => {
      setNoteDraft("");
      toast.show({ tone: "success", title: t("notes.savedToast") });
      void qc.invalidateQueries({ queryKey: ["org", orgId, "notes"] });
    },
    onError: (e) => toast.show({ tone: "error", title: getMessage(e) }),
  });

  // Gate on the profile-quality query as the representative "can I view this
  // partner's CRM record" check (403 → permission state, 404 → not-found state).
  if (qualityQuery.isError && qualityQuery.error instanceof ApiError) {
    const err = qualityQuery.error;
    if (err.isPermissionError) {
      return (
        <>
          <PageHeader title={t("title")} />
          <EmptyState kind="permission" icon={ShieldWarning} title={t("permissionTitle")} description={t("permissionBody")} />
        </>
      );
    }
    if (err.isAuthError) {
      return (
        <>
          <PageHeader title={t("title")} />
          <EmptyState kind="auth" icon={SignIn} title={tStates("authTitle")} description={tStates("authBody")} />
        </>
      );
    }
    if (err.code === "RESOURCE_NOT_FOUND") {
      return (
        <>
          <PageHeader title={t("title")} />
          <EmptyState kind="empty" icon={Buildings} title={t("notFoundTitle")} description={t("notFoundBody")} />
        </>
      );
    }
  }

  const staffMembers = staffQuery.data?.data ?? [];
  const owner = campusOwnerQuery.data?.campus_relationship_owner_id;

  const items: TabItem[] = [
    { value: "overview", label: t("tabs.overview"), icon: <ChartLineUp aria-hidden weight="duotone" className="size-4" /> },
    { value: "riskFlags", label: t("tabs.riskFlags"), icon: <Flag aria-hidden weight="duotone" className="size-4" /> },
    { value: "notes", label: t("tabs.notes"), icon: <NotePencil aria-hidden weight="duotone" className="size-4" /> },
    { value: "activity", label: t("tabs.activity"), icon: <UserCircle aria-hidden weight="duotone" className="size-4" /> },
  ];

  const riskFlagColumns: Column<OrgRiskFlag>[] = [
    {
      key: "type",
      header: t("riskFlags.type"),
      cell: (f) => <span className="font-medium text-[var(--text-primary)]">{f.flag_type}</span>,
    },
    {
      key: "severity",
      header: t("riskFlags.severity"),
      cell: (f) => (
        <StatusBadge tone={SEVERITY_TONE[f.severity]}>
          {t(SEVERITY_LABEL_KEY[f.severity] as never)}
        </StatusBadge>
      ),
    },
    {
      key: "status",
      header: t("riskFlags.status"),
      cell: (f) => (
        <StatusBadge tone={f.is_resolved ? "active" : "pending"}>
          {f.is_resolved ? t("riskFlags.resolved") : t("riskFlags.open")}
        </StatusBadge>
      ),
    },
    {
      key: "raised_at",
      header: t("riskFlags.raisedAt"),
      cell: (f) => formatDateTime(f.raised_at, locale),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      cell: (f) =>
        !f.is_resolved ? (
          <Button variant="ghost" size="sm" onClick={() => setResolving(f)}>
            {t("riskFlags.resolve")}
          </Button>
        ) : null,
    },
  ];

  return (
    <>
      <PageHeader
        title={registration?.company_name ?? t("title")}
        actions={
          <Link
            href="/university/partners"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          >
            <ArrowLeft aria-hidden weight="bold" className="size-4" />
            {t("backToList")}
          </Link>
        }
      />

      <Tabs items={items} value={tab} onValueChange={setTab} ariaLabel={t("title")} idBase={TABS_ID} className="mb-6" />

      <TabPanel tabsId={TABS_ID} value="overview" active={tab === "overview"}>
        <div className="grid gap-5 lg:grid-cols-2">
          <SectionCard title={t("profileQuality.title")} icon={ChartLineUp} iconGradient="icon-chip-primary">
            {qualityQuery.isPending ? (
              <Skeleton className="h-24 w-full" />
            ) : qualityQuery.data ? (
              <div className="space-y-3">
                <p className="text-2xl font-black text-[var(--text-primary)]">
                  {t("profileQuality.score", { score: qualityQuery.data.score })}
                </p>
                {qualityQuery.data.missing.length > 0 && (
                  <div>
                    <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                      {t("profileQuality.missingTitle")}
                    </p>
                    <ul className="flex flex-wrap gap-1.5">
                      {qualityQuery.data.missing.map((check) => (
                        <li
                          key={check}
                          className="rounded-md bg-[var(--amber-100)] px-2 py-1 text-xs font-medium text-[var(--amber-800)]"
                        >
                          {t.has(`profileQuality.check.${check}`)
                            ? t(`profileQuality.check.${check}` as never)
                            : check}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : null}
          </SectionCard>

          <SectionCard title={t("seats.title")} icon={UserCircle} iconGradient="icon-chip-info">
            {seatsQuery.isPending ? (
              <Skeleton className="h-10 w-full" />
            ) : seatsQuery.data ? (
              <div>
                <p className="text-sm font-semibold text-[var(--text-primary)]">
                  {seatsQuery.data.unlimited
                    ? t("seats.unlimited", { used: seatsQuery.data.used })
                    : t("seats.usage", { used: seatsQuery.data.used, max: seatsQuery.data.limit ?? 0 })}
                </p>
                {seatsQuery.data.at_capacity && (
                  <p className="mt-1 text-xs font-medium text-[var(--amber-700)]">{t("seats.atCapacity")}</p>
                )}
              </div>
            ) : null}
          </SectionCard>

          <SectionCard title={t("campusOwner.title")} description={t("campusOwner.intro")} icon={UserCircle} iconGradient="icon-chip-neutral" className="lg:col-span-2">
            {campusOwnerQuery.isPending ? (
              <Skeleton className="h-10 w-full" />
            ) : ownerEditing ? (
              <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                <div className="flex-1">
                  <Select
                    label={t("campusOwner.assign")}
                    value={ownerDraft}
                    onChange={(e) => setOwnerDraft(e.target.value)}
                    options={[
                      { value: "", label: t("campusOwner.selectPlaceholder") },
                      ...staffMembers
                        .filter((m) => m.user_id)
                        .map((m) => ({ value: m.user_id as string, label: m.full_name || m.user_email })),
                    ]}
                  />
                </div>
                <div className="flex gap-2">
                  <Button variant="ghost" onClick={() => setOwnerEditing(false)}>
                    {tc("cancel")}
                  </Button>
                  <Button
                    variant="primary"
                    loading={setOwner.isPending}
                    onClick={() => setOwner.mutate(ownerDraft || null)}
                  >
                    {t("campusOwner.save")}
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                    {t("campusOwner.current")}
                  </p>
                  <p className="mt-0.5 text-sm font-semibold text-[var(--text-primary)]">
                    {owner
                      ? staffMembers.find((m) => m.user_id === owner)?.full_name ?? owner
                      : t("campusOwner.none")}
                  </p>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    setOwnerDraft(owner ?? "");
                    setOwnerEditing(true);
                  }}
                >
                  {t("campusOwner.assign")}
                </Button>
              </div>
            )}
          </SectionCard>
        </div>
      </TabPanel>

      <TabPanel tabsId={TABS_ID} value="riskFlags" active={tab === "riskFlags"}>
        <SectionCard title={t("riskFlags.title")} description={t("riskFlags.intro")}>
          <div className="mb-4 flex justify-end">
            <Button variant="primary" size="sm" onClick={() => setRaiseOpen(true)}>
              <Plus aria-hidden weight="bold" className="size-4" />
              {t("riskFlags.raise")}
            </Button>
          </div>
          <DataTable
            columns={riskFlagColumns}
            rows={riskFlagsQuery.data ?? []}
            getRowId={(f) => f.id}
            loading={riskFlagsQuery.isPending}
            caption={t("riskFlags.title")}
            empty={{ kind: "empty", icon: Flag, title: t("riskFlags.empty") }}
          />
        </SectionCard>
      </TabPanel>

      <TabPanel tabsId={TABS_ID} value="notes" active={tab === "notes"}>
        <SectionCard title={t("notes.title")} description={t("notes.intro")}>
          <div className="mb-5 space-y-2">
            <Textarea
              label={t("notes.add")}
              placeholder={t("notes.placeholder")}
              rows={3}
              value={noteDraft}
              onChange={(e) => {
                setNoteDraft(e.target.value);
                if (noteError) setNoteError(null);
              }}
              error={noteError ?? undefined}
            />
            <div className="flex justify-end">
              <Button
                variant="primary"
                size="sm"
                loading={addNote.isPending}
                onClick={() => {
                  if (!noteDraft.trim()) {
                    setNoteError(t("notes.emptyError"));
                    return;
                  }
                  addNote.mutate();
                }}
              >
                {t("notes.save")}
              </Button>
            </div>
          </div>
          {notesQuery.isPending ? (
            <Skeleton className="h-20 w-full" />
          ) : (notesQuery.data ?? []).length === 0 ? (
            <EmptyState kind="empty" icon={NotePencil} title={t("notes.empty")} />
          ) : (
            <ul className="space-y-3">
              {(notesQuery.data ?? []).map((note: OrgNote) => (
                <li key={note.id} className="rounded-xl border border-[var(--border-default)] bg-white p-4">
                  <p className="text-sm text-[var(--text-primary)]">{note.body}</p>
                  <p className="mt-1.5 text-xs text-[var(--text-muted)]">
                    {formatDateTime(note.created_at, locale)}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </TabPanel>

      <TabPanel tabsId={TABS_ID} value="activity" active={tab === "activity"}>
        <div className="grid gap-5 lg:grid-cols-2">
          <SectionCard title={t("activity.eventsTitle")}>
            {activityQuery.isPending ? (
              <Skeleton className="h-16 w-full" />
            ) : activityQuery.data ? (
              <p className="text-sm text-[var(--text-secondary)]">
                {t("activity.total", { count: activityQuery.data.events.total })}
              </p>
            ) : null}
          </SectionCard>
          <SectionCard title={t("activity.campaignsTitle")}>
            {activityQuery.isPending ? (
              <Skeleton className="h-16 w-full" />
            ) : activityQuery.data ? (
              <p className="text-sm text-[var(--text-secondary)]">
                {t("activity.total", { count: activityQuery.data.campaigns.total })}
              </p>
            ) : null}
          </SectionCard>
          <SectionCard title={t("activity.hiringTitle", { months: hiringQuery.data?.window_months ?? 12 })} className="lg:col-span-2">
            {hiringQuery.isPending ? (
              <Skeleton className="h-20 w-full" />
            ) : hiringQuery.data ? (
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <Stat label={t("activity.totalApplications")} value={hiringQuery.data.total_applications} />
                <Stat label={t("activity.hired")} value={hiringQuery.data.hired} />
                <Stat label={t("activity.offersAccepted")} value={hiringQuery.data.offers_accepted} />
                <Stat label={t("activity.recentApplications")} value={hiringQuery.data.recent_applications} />
              </div>
            ) : null}
          </SectionCard>
        </div>
      </TabPanel>

      {/* Raise risk flag */}
      <Modal
        open={raiseOpen}
        onClose={() => setRaiseOpen(false)}
        title={t("riskFlags.raiseTitle")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setRaiseOpen(false)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="danger"
              disabled={!flagType.trim()}
              loading={raiseFlag.isPending}
              onClick={() => raiseFlag.mutate()}
            >
              {t("riskFlags.raiseConfirm")}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="mb-1.5 block text-sm font-semibold text-[var(--text-primary)]">
              {t("riskFlags.type")}
            </label>
            <input
              value={flagType}
              onChange={(e) => setFlagType(e.target.value)}
              placeholder={t("riskFlags.typePlaceholder")}
              className="w-full rounded-xl border border-[var(--border-default)] bg-white px-3.5 py-2.5 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--brand-primary)]/50 focus:ring-2 focus:ring-[var(--brand-primary)]/30"
            />
          </div>
          <Select
            label={t("riskFlags.severity")}
            value={flagSeverity}
            onChange={(e) => setFlagSeverity(e.target.value as RiskFlagSeverity)}
            options={[
              { value: "low", label: t("riskFlags.severityLow") },
              { value: "medium", label: t("riskFlags.severityMedium") },
              { value: "high", label: t("riskFlags.severityHigh") },
            ]}
          />
          <Textarea
            label={t("riskFlags.note")}
            rows={3}
            value={flagNote}
            onChange={(e) => setFlagNote(e.target.value)}
          />
        </div>
      </Modal>

      {/* Resolve risk flag */}
      <Modal
        open={resolving !== null}
        onClose={() => setResolving(null)}
        title={t("riskFlags.resolveTitle")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setResolving(null)}>
              {tc("cancel")}
            </Button>
            <Button
              variant="primary"
              loading={resolveFlag.isPending}
              onClick={() => resolving && resolveFlag.mutate(resolving)}
            >
              <CheckCircle aria-hidden weight="bold" className="size-4" />
              {t("riskFlags.resolveConfirm")}
            </Button>
          </>
        }
      >
        <Textarea
          label={t("riskFlags.resolutionNote")}
          rows={3}
          value={resolutionNote}
          onChange={(e) => setResolutionNote(e.target.value)}
        />
      </Modal>
    </>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">{value}</p>
      <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{label}</p>
    </div>
  );
}
