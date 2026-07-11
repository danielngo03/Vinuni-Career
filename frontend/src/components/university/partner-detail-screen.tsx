"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowLeft,
  Check,
  Flag,
  Gauge,
  Plus,
  StickyNote,
  UserCircle,
} from "lucide-react";
import { Link } from "@/i18n/navigation";
import {
  Button,
  Input,
  Modal,
  Select,
  Textarea,
  Tabs,
  TabPanel,
  useToast,
  type TabItem,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  CardToolbar,
  DataTable,
  type ColumnDef,
  EmptyState,
  KpiRow,
  KpiTile,
  StatusChip,
  type ChipTone,
} from "@/components/kit";
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

const SEVERITY_CHIP: Record<RiskFlagSeverity, ChipTone> = {
  low: "info",
  medium: "warning",
  high: "danger",
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

  const [tab, setTab] = React.useState("overview");
  const [ownerDraft, setOwnerDraft] = React.useState<string>("");
  const [ownerEditing, setOwnerEditing] = React.useState(false);
  const [raiseOpen, setRaiseOpen] = React.useState(false);
  const [flagType, setFlagType] = React.useState("");
  const [flagSeverity, setFlagSeverity] = React.useState<RiskFlagSeverity>("medium");
  const [flagNote, setFlagNote] = React.useState("");
  const [resolving, setResolving] = React.useState<OrgRiskFlag | null>(null);
  const [resolutionNote, setResolutionNote] = React.useState("");
  const [noteDraft, setNoteDraft] = React.useState("");
  const [noteError, setNoteError] = React.useState<string | null>(null);

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
    mutationFn: (ownerUserId: string | null) => organizationApi.setCampusOwner(orgId, ownerUserId),
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

  const staffMembers = staffQuery.data?.data ?? [];
  const owner = campusOwnerQuery.data?.campus_relationship_owner_id;

  const items: TabItem[] = [
    { value: "overview", label: t("tabs.overview"), icon: <Gauge aria-hidden className="size-4" strokeWidth={1.8} /> },
    { value: "riskFlags", label: t("tabs.riskFlags"), icon: <Flag aria-hidden className="size-4" strokeWidth={1.8} /> },
    { value: "notes", label: t("tabs.notes"), icon: <StickyNote aria-hidden className="size-4" strokeWidth={1.8} /> },
    { value: "activity", label: t("tabs.activity"), icon: <Activity aria-hidden className="size-4" strokeWidth={1.8} /> },
  ];

  const riskFlagColumns: ColumnDef<OrgRiskFlag, unknown>[] = [
    {
      accessorKey: "flag_type",
      header: t("riskFlags.type"),
      cell: ({ row }) => <span className="font-semibold text-foreground">{row.original.flag_type}</span>,
    },
    {
      accessorKey: "severity",
      header: t("riskFlags.severity"),
      cell: ({ row }) => (
        <StatusChip tone={SEVERITY_CHIP[row.original.severity]} dot>
          {t(SEVERITY_LABEL_KEY[row.original.severity] as never)}
        </StatusChip>
      ),
    },
    {
      accessorKey: "is_resolved",
      header: t("riskFlags.status"),
      cell: ({ row }) => (
        <StatusChip tone={row.original.is_resolved ? "success" : "warning"} dot>
          {row.original.is_resolved ? t("riskFlags.resolved") : t("riskFlags.open")}
        </StatusChip>
      ),
    },
    {
      accessorKey: "raised_at",
      header: t("riskFlags.raisedAt"),
      cell: ({ row }) => (
        <span className="whitespace-nowrap type-small text-muted-foreground">
          {formatDateTime(row.original.raised_at, locale)}
        </span>
      ),
    },
    {
      id: "actions",
      header: "",
      meta: { align: "right" },
      enableSorting: false,
      cell: ({ row }) =>
        !row.original.is_resolved ? (
          <Button variant="ghost" size="sm" onClick={() => setResolving(row.original)}>
            {t("riskFlags.resolve")}
          </Button>
        ) : null,
    },
  ];

  const header = (
    <PageHeader
      title={registration?.company_name ?? t("title")}
      actions={
        <Link href="/university/partners">
          <Button variant="secondary" size="sm">
            <ArrowLeft className="size-4" strokeWidth={1.8} />
            {t("backToList")}
          </Button>
        </Link>
      }
    />
  );

  // Gate on the profile-quality query (403 → permission, 401 → auth, 404 → not found).
  if (qualityQuery.isError && qualityQuery.error instanceof ApiError) {
    const err = qualityQuery.error;
    if (err.isPermissionError) {
      return (
        <>
          <PageHeader title={t("title")} />
          <EmptyState kind="permission" title={t("permissionTitle")} description={t("permissionBody")} />
        </>
      );
    }
    if (err.isAuthError) {
      return (
        <>
          <PageHeader title={t("title")} />
          <EmptyState kind="auth" title={tStates("authTitle")} description={tStates("authBody")} />
        </>
      );
    }
    if (err.code === "RESOURCE_NOT_FOUND") {
      return (
        <>
          <PageHeader title={t("title")} />
          <EmptyState kind="empty" title={t("notFoundTitle")} description={t("notFoundBody")} />
        </>
      );
    }
  }

  return (
    <>
      {header}

      <Tabs items={items} value={tab} onValueChange={setTab} ariaLabel={t("title")} idBase={TABS_ID} className="mb-6" />

      {/* Overview */}
      <TabPanel tabsId={TABS_ID} value="overview" active={tab === "overview"}>
        <div className="space-y-4">
          <KpiRow cols={3}>
            <KpiTile
              label={t("profileQuality.title")}
              value={qualityQuery.data ? t("profileQuality.score", { score: qualityQuery.data.score }) : "—"}
              icon={Gauge}
            />
            <KpiTile
              label={t("seats.title")}
              value={
                seatsQuery.data
                  ? seatsQuery.data.unlimited
                    ? String(seatsQuery.data.used)
                    : `${seatsQuery.data.used}/${seatsQuery.data.limit ?? 0}`
                  : "—"
              }
              icon={UserCircle}
              hint={seatsQuery.data?.at_capacity ? t("seats.atCapacity") : undefined}
            />
            <KpiTile
              label={t("riskFlags.title")}
              value={riskFlagsQuery.data ? String(riskFlagsQuery.data.filter((f) => !f.is_resolved).length) : "—"}
              icon={Flag}
            />
          </KpiRow>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>{t("profileQuality.title")}</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                {qualityQuery.isPending ? (
                  <div className="h-24 animate-skeleton rounded-lg bg-[var(--bg-muted)]" />
                ) : qualityQuery.data ? (
                  <div className="space-y-3">
                    <p className="type-metric text-foreground">{t("profileQuality.score", { score: qualityQuery.data.score })}</p>
                    {qualityQuery.data.missing.length > 0 && (
                      <div>
                        <p className="mb-1.5 text-[0.6875rem] font-semibold uppercase tracking-wide text-muted-foreground">
                          {t("profileQuality.missingTitle")}
                        </p>
                        <div className="flex flex-wrap gap-1.5">
                          {qualityQuery.data.missing.map((check) => (
                            <StatusChip key={check} tone="warning" size="sm">
                              {t.has(`profileQuality.check.${check}`)
                                ? t(`profileQuality.check.${check}` as never)
                                : check}
                            </StatusChip>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : null}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div>
                  <CardTitle>{t("campusOwner.title")}</CardTitle>
                  <CardDescription>{t("campusOwner.intro")}</CardDescription>
                </div>
              </CardHeader>
              <CardContent>
                {campusOwnerQuery.isPending ? (
                  <div className="h-10 animate-skeleton rounded-lg bg-[var(--bg-muted)]" />
                ) : ownerEditing ? (
                  <div className="flex flex-col gap-3">
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
                    <div className="flex justify-end gap-2">
                      <Button variant="ghost" size="sm" onClick={() => setOwnerEditing(false)}>
                        {tc("cancel")}
                      </Button>
                      <Button variant="primary" size="sm" loading={setOwner.isPending} onClick={() => setOwner.mutate(ownerDraft || null)}>
                        {t("campusOwner.save")}
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[0.6875rem] font-semibold uppercase tracking-wide text-muted-foreground">
                        {t("campusOwner.current")}
                      </p>
                      <p className="mt-0.5 truncate text-[0.8125rem] font-semibold text-foreground">
                        {owner ? staffMembers.find((m) => m.user_id === owner)?.full_name ?? owner : t("campusOwner.none")}
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
              </CardContent>
            </Card>
          </div>
        </div>
      </TabPanel>

      {/* Risk flags */}
      <TabPanel tabsId={TABS_ID} value="riskFlags" active={tab === "riskFlags"}>
        <Card>
          <CardHeader>
            <div>
              <CardTitle>{t("riskFlags.title")}</CardTitle>
              <CardDescription>{t("riskFlags.intro")}</CardDescription>
            </div>
            <CardToolbar>
              <Button variant="primary" size="sm" onClick={() => setRaiseOpen(true)}>
                <Plus className="size-4" strokeWidth={2} />
                {t("riskFlags.raise")}
              </Button>
            </CardToolbar>
          </CardHeader>
          <CardContent>
            <DataTable
              columns={riskFlagColumns}
              data={riskFlagsQuery.data ?? []}
              getRowId={(f) => f.id}
              loading={riskFlagsQuery.isPending}
              empty={<EmptyState kind="empty" title={t("riskFlags.empty")} />}
            />
          </CardContent>
        </Card>
      </TabPanel>

      {/* Notes */}
      <TabPanel tabsId={TABS_ID} value="notes" active={tab === "notes"}>
        <Card>
          <CardHeader>
            <div>
              <CardTitle>{t("notes.title")}</CardTitle>
              <CardDescription>{t("notes.intro")}</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="space-y-2">
              <Textarea
                label={t("notes.add")}
                placeholder={t("notes.placeholder")}
                rows={3}
                value={noteDraft}
                error={noteError ?? undefined}
                onChange={(e) => {
                  setNoteDraft(e.target.value);
                  if (noteError) setNoteError(null);
                }}
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
              <div className="h-20 animate-skeleton rounded-lg bg-[var(--bg-muted)]" />
            ) : (notesQuery.data ?? []).length === 0 ? (
              <EmptyState kind="empty" title={t("notes.empty")} />
            ) : (
              <ul className="space-y-2.5">
                {(notesQuery.data ?? []).map((note: OrgNote) => (
                  <li key={note.id} className="rounded-xl border border-border bg-[var(--bg-subtle)] p-4">
                    <p className="text-[0.8125rem] text-foreground">{note.body}</p>
                    <p className="mt-1.5 type-caption text-muted-foreground">{formatDateTime(note.created_at, locale)}</p>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </TabPanel>

      {/* Activity */}
      <TabPanel tabsId={TABS_ID} value="activity" active={tab === "activity"}>
        <div className="space-y-4">
          <KpiRow cols={4}>
            <KpiTile
              label={t("activity.totalApplications")}
              value={hiringQuery.data ? String(hiringQuery.data.total_applications) : "—"}
              icon={Activity}
            />
            <KpiTile label={t("activity.hired")} value={hiringQuery.data ? String(hiringQuery.data.hired) : "—"} icon={Check} />
            <KpiTile
              label={t("activity.offersAccepted")}
              value={hiringQuery.data ? String(hiringQuery.data.offers_accepted) : "—"}
              icon={Check}
            />
            <KpiTile
              label={t("activity.recentApplications")}
              value={hiringQuery.data ? String(hiringQuery.data.recent_applications) : "—"}
              icon={Activity}
            />
          </KpiRow>

          <div className="grid gap-4 sm:grid-cols-2">
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>{t("activity.eventsTitle")}</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                {activityQuery.isPending ? (
                  <div className="h-6 animate-skeleton rounded bg-[var(--bg-muted)]" />
                ) : activityQuery.data ? (
                  <p className="type-metric text-foreground">{activityQuery.data.events.total}</p>
                ) : null}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>{t("activity.campaignsTitle")}</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                {activityQuery.isPending ? (
                  <div className="h-6 animate-skeleton rounded bg-[var(--bg-muted)]" />
                ) : activityQuery.data ? (
                  <p className="type-metric text-foreground">{activityQuery.data.campaigns.total}</p>
                ) : null}
              </CardContent>
            </Card>
          </div>
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
            <Button variant="danger" disabled={!flagType.trim()} loading={raiseFlag.isPending} onClick={() => raiseFlag.mutate()}>
              {t("riskFlags.raiseConfirm")}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label={t("riskFlags.type")}
            placeholder={t("riskFlags.typePlaceholder")}
            value={flagType}
            onChange={(e) => setFlagType(e.target.value)}
          />
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
          <Textarea label={t("riskFlags.note")} rows={3} value={flagNote} onChange={(e) => setFlagNote(e.target.value)} />
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
            <Button variant="primary" loading={resolveFlag.isPending} onClick={() => resolving && resolveFlag.mutate(resolving)}>
              <Check className="size-4" strokeWidth={2} />
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
