"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  CheckCircle2,
  Eye,
  FilePlus2,
  Layers,
  Mail,
  Pencil,
  X,
} from "lucide-react";
import { Button, Input, Modal, Select, Textarea, useToast } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import {
  Card,
  CardContent,
  DataTable,
  DetailSheet,
  DetailSheetSection,
  DetailRow,
  EmptyState,
  FilterBar,
  KpiRow,
  KpiTile,
  StatusChip,
  type ChipTone,
  type ColumnDef,
} from "@/components/kit";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import {
  ApiError,
  templateAdminApi,
  NOTIFICATION_TEMPLATE_CHANNELS,
  NOTIFICATION_TEMPLATE_LOCALES,
  NOTIFICATION_TEMPLATE_STATUSES,
  type NotificationTemplate,
  type NotificationTemplatePreviewResult,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";

const STATUS_TONE: Record<string, ChipTone> = {
  draft: "neutral",
  active: "success",
  archived: "amber",
};

type TemplateForm = {
  key: string;
  channel: string;
  locale: string;
  subject: string;
  title: string;
  body: string;
  allowed: string[];
  required: string[];
};

function emptyForm(): TemplateForm {
  return { key: "", channel: "email", locale: "vi", subject: "", title: "", body: "", allowed: [], required: [] };
}

function formFromTemplate(template: NotificationTemplate): TemplateForm {
  return {
    key: template.key,
    channel: template.channel,
    locale: template.locale,
    subject: template.subject ?? "",
    title: template.title ?? "",
    body: template.body,
    allowed: template.variables_schema?.allowed ?? [],
    required: template.variables_schema?.required ?? [],
  };
}

/** Removable variable chip input (Enter/comma adds; click × removes). */
function TagInput({
  label,
  values,
  onChange,
  help,
}: {
  label: string;
  values: string[];
  onChange: (values: string[]) => void;
  help?: string;
}) {
  const [draft, setDraft] = React.useState("");

  function commit() {
    const v = draft.trim();
    if (v && !values.includes(v)) onChange([...values, v]);
    setDraft("");
  }

  return (
    <div>
      <label className="mb-1.5 block text-sm font-semibold text-foreground">{label}</label>
      <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-border bg-card px-2.5 py-2">
        {values.map((v) => (
          <span
            key={v}
            className="inline-flex items-center gap-1 rounded-full bg-[var(--bg-muted)] px-2.5 py-1 font-mono text-xs text-foreground"
          >
            {v}
            <button
              type="button"
              onClick={() => onChange(values.filter((item) => item !== v))}
              aria-label={`Remove ${v}`}
              className="text-muted-foreground hover:text-[var(--content-danger)]"
            >
              <X aria-hidden className="size-3" strokeWidth={2.2} />
            </button>
          </span>
        ))}
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              commit();
            }
          }}
          onBlur={commit}
          placeholder="student_name"
          className="min-w-[120px] flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
        />
      </div>
      {help && <p className="mt-1 type-caption text-muted-foreground">{help}</p>}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Screen                                                                       */
/* -------------------------------------------------------------------------- */

export function NotificationTemplatesAdminScreen() {
  const t = useTranslations("notificationTemplates");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const toast = useToast();
  const qc = useQueryClient();
  const getErrorMessage = useApiErrorMessage();

  const [keyFilter, setKeyFilter] = React.useState("");
  const [channelFilter, setChannelFilter] = React.useState("");
  const [localeFilter, setLocaleFilter] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState("");

  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [formOpen, setFormOpen] = React.useState(false);
  const [editingTemplate, setEditingTemplate] = React.useState<NotificationTemplate | null>(null);
  const [asNewVersion, setAsNewVersion] = React.useState(false);
  const [form, setForm] = React.useState<TemplateForm>(emptyForm());
  const [formError, setFormError] = React.useState<string | null>(null);

  const [previewTarget, setPreviewTarget] = React.useState<NotificationTemplate | null>(null);
  const [sampleVars, setSampleVars] = React.useState<Record<string, string>>({});
  const [previewResult, setPreviewResult] = React.useState<NotificationTemplatePreviewResult | null>(null);

  const [confirmAction, setConfirmAction] = React.useState<{
    kind: "activate" | "archive";
    template: NotificationTemplate;
  } | null>(null);

  const query = useQuery({
    queryKey: ["admin", "notification-templates", keyFilter, channelFilter, localeFilter, statusFilter],
    queryFn: () =>
      templateAdminApi.list({
        key: keyFilter.trim() || undefined,
        channel: channelFilter || undefined,
        locale: localeFilter || undefined,
        status: statusFilter || undefined,
      }),
    retry: false,
  });

  const templates = React.useMemo(() => query.data ?? [], [query.data]);
  const selected = React.useMemo(
    () => templates.find((x) => x.id === selectedId) ?? null,
    [templates, selectedId],
  );

  const stats = React.useMemo(() => {
    const active = templates.filter((x) => x.status === "active").length;
    const draft = templates.filter((x) => x.status === "draft").length;
    return { total: templates.length, active, draft };
  }, [templates]);

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["admin", "notification-templates"] });
  }

  function closeAllModals() {
    setSelectedId(null);
    setPreviewTarget(null);
    setConfirmAction(null);
  }

  function openCreate() {
    closeAllModals();
    setEditingTemplate(null);
    setAsNewVersion(false);
    setForm(emptyForm());
    setFormError(null);
    setFormOpen(true);
  }

  function openEdit(template: NotificationTemplate) {
    setSelectedId(null);
    setEditingTemplate(template);
    setAsNewVersion(false);
    setForm(formFromTemplate(template));
    setFormError(null);
    setFormOpen(true);
  }

  function openNewVersion(template: NotificationTemplate) {
    setSelectedId(null);
    setEditingTemplate(template);
    setAsNewVersion(true);
    setForm(formFromTemplate(template));
    setFormError(null);
    setFormOpen(true);
  }

  function openPreview(template: NotificationTemplate) {
    setSelectedId(null);
    setPreviewTarget(template);
    setPreviewResult(null);
    const initial: Record<string, string> = {};
    for (const name of template.variables_schema?.allowed ?? []) initial[name] = `[${name}]`;
    setSampleVars(initial);
  }

  const isEditingDraft = editingTemplate !== null && !asNewVersion;

  const create = useMutation({
    mutationFn: () =>
      templateAdminApi.create({
        key: form.key.trim(),
        channel: form.channel,
        locale: form.locale,
        subject: form.subject.trim() || undefined,
        title: form.title.trim() || undefined,
        body: form.body,
        variables_schema: { allowed: form.allowed, required: form.required },
      }),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("createdToast") });
      setFormOpen(false);
      refresh();
    },
    onError: (e) => setFormError(describeTemplateError(e, getErrorMessage)),
  });

  const update = useMutation({
    mutationFn: () => {
      if (!editingTemplate) throw new Error("missing_template");
      return templateAdminApi.update(editingTemplate.id, {
        subject: form.subject.trim() || undefined,
        title: form.title.trim() || undefined,
        body: form.body,
        variables_schema: { allowed: form.allowed, required: form.required },
      });
    },
    onSuccess: () => {
      toast.show({ tone: "success", title: t("updatedToast") });
      setFormOpen(false);
      refresh();
    },
    onError: (e) => setFormError(describeTemplateError(e, getErrorMessage)),
  });

  const activate = useMutation({
    mutationFn: (template: NotificationTemplate) => templateAdminApi.activate(template.id),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("activatedToast") });
      setConfirmAction(null);
      refresh();
    },
    onError: (e) => {
      toast.show({ tone: "error", title: getErrorMessage(e) });
      setConfirmAction(null);
    },
  });

  const archive = useMutation({
    mutationFn: (template: NotificationTemplate) => templateAdminApi.archive(template.id),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("archivedToast") });
      setConfirmAction(null);
      refresh();
    },
    onError: (e) => {
      toast.show({ tone: "error", title: getErrorMessage(e) });
      setConfirmAction(null);
    },
  });

  const preview = useMutation({
    mutationFn: (template: NotificationTemplate) => templateAdminApi.preview(template.id, sampleVars),
    onSuccess: (data) => setPreviewResult(data),
    onError: (e) => toast.show({ tone: "error", title: getErrorMessage(e) }),
  });

  const header = (
    <PageHeader
      title={t("title")}
      subtitle={t("subtitle")}
      actions={
        <Button variant="primary" size="sm" onClick={openCreate}>
          <FilePlus2 className="size-4" strokeWidth={2} />
          {t("create")}
        </Button>
      }
    />
  );

  /* ---- Permission / auth states ---- */
  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          {header}
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            title={err.isPermissionError ? tStates("permissionTitle") : tStates("authTitle")}
            description={err.isPermissionError ? t("permissionBody") : tStates("authBody")}
          />
        </>
      );
    }
  }

  const submitting = create.isPending || update.isPending;

  const columns: ColumnDef<NotificationTemplate, unknown>[] = [
    {
      accessorKey: "key",
      header: t("colKey"),
      cell: ({ row }) => (
        <div className="min-w-0">
          <span className="block truncate font-mono text-[0.8125rem] font-semibold text-foreground">
            {row.original.key}
          </span>
          {row.original.subject && (
            <span className="type-caption block truncate text-muted-foreground">{row.original.subject}</span>
          )}
        </div>
      ),
    },
    {
      accessorKey: "channel",
      header: t("colChannel"),
      cell: ({ row }) => (
        <StatusChip tone="indigo" size="sm">
          {t(`channels.${row.original.channel}`)}
        </StatusChip>
      ),
    },
    {
      accessorKey: "locale",
      header: t("colLocale"),
      cell: ({ row }) => <span className="uppercase text-muted-foreground">{row.original.locale}</span>,
    },
    {
      accessorKey: "version",
      header: t("colVersion"),
      meta: { align: "right" },
      cell: ({ row }) => <span className="tabular-nums text-muted-foreground">v{row.original.version}</span>,
    },
    {
      accessorKey: "status",
      header: t("colStatus"),
      cell: ({ row }) => (
        <StatusChip tone={STATUS_TONE[row.original.status] ?? "neutral"} dot size="sm">
          {t(`statuses.${row.original.status}`)}
        </StatusChip>
      ),
    },
    {
      accessorKey: "activated_at",
      header: t("colActivated"),
      meta: { align: "right" },
      cell: ({ row }) => (
        <span className="type-caption tabular-nums text-muted-foreground">
          {row.original.activated_at ? formatDateTime(row.original.activated_at, locale) : t("neverActivated")}
        </span>
      ),
    },
  ];

  const loadError =
    query.isError &&
    !(query.error instanceof ApiError && (query.error.isPermissionError || query.error.isAuthError));

  return (
    <>
      {header}

      <div className="space-y-4">
        <KpiRow cols={3}>
          <KpiTile label={t("kpiTotal")} value={String(stats.total)} icon={Layers} />
          <KpiTile label={t("kpiActive")} value={String(stats.active)} icon={CheckCircle2} />
          <KpiTile label={t("kpiDraft")} value={String(stats.draft)} icon={Pencil} />
        </KpiRow>

        <FilterBar
          search={{
            value: keyFilter,
            onChange: setKeyFilter,
            placeholder: t("filterKeyPlaceholder"),
            ariaLabel: t("filterKey"),
          }}
        >
          <div className="w-36 sm:w-40">
            <Select
              aria-label={t("filterChannel")}
              value={channelFilter}
              onChange={(e) => setChannelFilter(e.target.value)}
              options={[
                { value: "", label: t("filterChannel") },
                ...NOTIFICATION_TEMPLATE_CHANNELS.map((c) => ({ value: c, label: t(`channels.${c}`) })),
              ]}
            />
          </div>
          <div className="w-28 sm:w-32">
            <Select
              aria-label={t("filterLocale")}
              value={localeFilter}
              onChange={(e) => setLocaleFilter(e.target.value)}
              options={[
                { value: "", label: t("filterLocale") },
                ...NOTIFICATION_TEMPLATE_LOCALES.map((l) => ({ value: l, label: l.toUpperCase() })),
              ]}
            />
          </div>
          <div className="w-32 sm:w-36">
            <Select
              aria-label={t("filterStatus")}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              options={[
                { value: "", label: t("filterStatus") },
                ...NOTIFICATION_TEMPLATE_STATUSES.map((s) => ({ value: s, label: t(`statuses.${s}`) })),
              ]}
            />
          </div>
        </FilterBar>

        {loadError ? (
          <EmptyState
            kind="error"
            title={tStates("errorTitle")}
            description={tStates("errorBody")}
            action={
              <Button variant="secondary" onClick={() => query.refetch()}>
                {tc("retry")}
              </Button>
            }
          />
        ) : (
          <Card>
            <CardContent className="pt-5">
              <DataTable
                columns={columns}
                data={templates}
                getRowId={(r) => r.id}
                loading={query.isPending}
                onRowClick={(r) => setSelectedId(r.id)}
                activeRowId={selectedId ?? undefined}
                pageSize={12}
                empty={
                  <EmptyState
                    kind="empty"
                    title={t("emptyTitle")}
                    description={t("emptyBody")}
                    action={
                      <Button variant="primary" onClick={openCreate}>
                        <FilePlus2 className="size-4" strokeWidth={2} />
                        {t("create")}
                      </Button>
                    }
                  />
                }
              />
            </CardContent>
          </Card>
        )}
      </div>

      {/* Detail sheet — template editor hub */}
      <TemplateDetailSheet
        template={selected}
        locale={locale}
        onClose={() => setSelectedId(null)}
        onEdit={openEdit}
        onNewVersion={openNewVersion}
        onPreview={openPreview}
        onActivate={(tpl) => {
          setSelectedId(null);
          setConfirmAction({ kind: "activate", template: tpl });
        }}
        onArchive={(tpl) => {
          setSelectedId(null);
          setConfirmAction({ kind: "archive", template: tpl });
        }}
      />

      {/* Create / edit draft modal */}
      <Modal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        title={isEditingDraft ? t("editTitle") : t("createTitle")}
        description={t("formHint")}
        size="lg"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setFormOpen(false)} disabled={submitting}>
              {tc("cancel")}
            </Button>
            <Button loading={submitting} onClick={() => (isEditingDraft ? update.mutate() : create.mutate())}>
              {tc("save")}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {formError && (
            <p role="alert" className="rounded-lg px-3 py-2 text-xs font-medium" style={{ background: "var(--content-danger-soft)", color: "var(--content-danger)" }}>
              {formError}
            </p>
          )}
          <div className="grid gap-4 md:grid-cols-3">
            <Input
              label={t("key")}
              required
              disabled={isEditingDraft || asNewVersion}
              value={form.key}
              onChange={(e) => setForm((prev) => ({ ...prev, key: e.target.value }))}
              help={t("keyHelp")}
            />
            <Select
              label={t("channel")}
              required
              disabled={isEditingDraft || asNewVersion}
              value={form.channel}
              onChange={(e) => setForm((prev) => ({ ...prev, channel: e.target.value }))}
              options={NOTIFICATION_TEMPLATE_CHANNELS.map((c) => ({ value: c, label: t(`channels.${c}`) }))}
            />
            <Select
              label={t("locale")}
              required
              disabled={isEditingDraft || asNewVersion}
              value={form.locale}
              onChange={(e) => setForm((prev) => ({ ...prev, locale: e.target.value }))}
              options={NOTIFICATION_TEMPLATE_LOCALES.map((l) => ({ value: l, label: l.toUpperCase() }))}
            />
          </div>
          <Input
            label={t("subject")}
            value={form.subject}
            onChange={(e) => setForm((prev) => ({ ...prev, subject: e.target.value }))}
            help={t("subjectHelp")}
          />
          <Input
            label={t("titleField")}
            value={form.title}
            onChange={(e) => setForm((prev) => ({ ...prev, title: e.target.value }))}
          />
          <Textarea
            label={t("body")}
            required
            rows={6}
            value={form.body}
            onChange={(e) => setForm((prev) => ({ ...prev, body: e.target.value }))}
            help={t("bodyHelp")}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <TagInput
              label={t("allowedVars")}
              values={form.allowed}
              onChange={(values) => setForm((prev) => ({ ...prev, allowed: values }))}
              help={t("allowedVarsHelp")}
            />
            <TagInput
              label={t("requiredVars")}
              values={form.required}
              onChange={(values) => setForm((prev) => ({ ...prev, required: values }))}
              help={t("requiredVarsHelp")}
            />
          </div>
        </div>
      </Modal>

      {/* Preview modal */}
      <Modal
        open={previewTarget !== null}
        onClose={() => setPreviewTarget(null)}
        title={t("previewTitle")}
        description={previewTarget ? `${previewTarget.key} · ${previewTarget.locale}` : undefined}
        size="lg"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setPreviewTarget(null)}>
              {tc("close")}
            </Button>
            <Button variant="primary" loading={preview.isPending} onClick={() => previewTarget && preview.mutate(previewTarget)}>
              {t("renderPreview")}
            </Button>
          </>
        }
      >
        {previewTarget && (
          <div className="space-y-4">
            {(previewTarget.variables_schema?.allowed ?? []).length > 0 && (
              <div className="grid gap-3 sm:grid-cols-2">
                {(previewTarget.variables_schema?.allowed ?? []).map((name) => (
                  <Input
                    key={name}
                    label={name}
                    value={sampleVars[name] ?? ""}
                    onChange={(e) => setSampleVars((prev) => ({ ...prev, [name]: e.target.value }))}
                  />
                ))}
              </div>
            )}
            {previewResult ? (
              <div className="space-y-3 rounded-xl border border-border bg-[var(--bg-subtle)] p-4">
                {previewResult.subject && <PreviewField label={t("subject")}>{previewResult.subject}</PreviewField>}
                {previewResult.title && <PreviewField label={t("titleField")}>{previewResult.title}</PreviewField>}
                <PreviewField label={t("body")}>
                  <span className="whitespace-pre-wrap">{previewResult.body}</span>
                </PreviewField>
                {previewResult.required_variables.length > 0 && (
                  <PreviewField label={t("requiredVars")}>{previewResult.required_variables.join(", ")}</PreviewField>
                )}
              </div>
            ) : (
              <p className="type-small text-muted-foreground">{t("previewHint")}</p>
            )}
          </div>
        )}
      </Modal>

      {/* Activate / archive confirm modal */}
      <Modal
        open={confirmAction !== null}
        onClose={() => setConfirmAction(null)}
        title={confirmAction?.kind === "activate" ? t("activateConfirmTitle") : t("archiveConfirmTitle")}
        description={confirmAction?.kind === "activate" ? t("activateConfirmBody") : t("archiveConfirmBody")}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmAction(null)}>
              {tc("cancel")}
            </Button>
            <Button
              variant={confirmAction?.kind === "archive" ? "danger" : "primary"}
              loading={activate.isPending || archive.isPending}
              onClick={() => {
                if (!confirmAction) return;
                if (confirmAction.kind === "activate") activate.mutate(confirmAction.template);
                else archive.mutate(confirmAction.template);
              }}
            >
              {confirmAction?.kind === "activate" ? t("activate") : t("archive")}
            </Button>
          </>
        }
      >
        <p className="type-small text-muted-foreground">
          {confirmAction?.template.key} · v{confirmAction?.template.version}
        </p>
      </Modal>
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Detail sheet                                                                 */
/* -------------------------------------------------------------------------- */

function TemplateDetailSheet({
  template,
  locale,
  onClose,
  onEdit,
  onNewVersion,
  onPreview,
  onActivate,
  onArchive,
}: {
  template: NotificationTemplate | null;
  locale: string;
  onClose: () => void;
  onEdit: (template: NotificationTemplate) => void;
  onNewVersion: (template: NotificationTemplate) => void;
  onPreview: (template: NotificationTemplate) => void;
  onActivate: (template: NotificationTemplate) => void;
  onArchive: (template: NotificationTemplate) => void;
}) {
  const t = useTranslations("notificationTemplates");
  const tc = useTranslations("common");
  const open = template != null;
  const allowed = template?.variables_schema?.allowed ?? [];
  const required = template?.variables_schema?.required ?? [];

  return (
    <DetailSheet
      open={open}
      onClose={onClose}
      ariaLabel={template?.key}
      title={template ? <span className="font-mono text-[0.9375rem]">{template.key}</span> : ""}
      subtitle={template ? `${t(`channels.${template.channel}`)} · ${template.locale.toUpperCase()} · v${template.version}` : undefined}
      status={
        template ? (
          <StatusChip tone={STATUS_TONE[template.status] ?? "neutral"} dot>
            {t(`statuses.${template.status}`)}
          </StatusChip>
        ) : undefined
      }
      width="lg"
      closeLabel={tc("close")}
      footer={
        template ? (
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => onPreview(template)}>
              <Eye className="size-4" strokeWidth={1.8} />
              {t("preview")}
            </Button>
            {template.status === "draft" && (
              <Button variant="secondary" size="sm" onClick={() => onEdit(template)}>
                <Pencil className="size-4" strokeWidth={1.8} />
                {t("edit")}
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={() => onNewVersion(template)}>
              <FilePlus2 className="size-4" strokeWidth={1.8} />
              {t("newVersion")}
            </Button>
            {template.status !== "archived" && (
              <Button variant="ghost" size="sm" onClick={() => onArchive(template)}>
                <Archive className="size-4" strokeWidth={1.8} />
                {t("archive")}
              </Button>
            )}
            {template.status !== "active" && (
              <Button variant="primary" size="sm" onClick={() => onActivate(template)}>
                <CheckCircle2 className="size-4" strokeWidth={1.8} />
                {t("activate")}
              </Button>
            )}
          </div>
        ) : undefined
      }
    >
      {template && (
        <>
          <DetailSheetSection title={t("metaSection")}>
            <dl>
              <DetailRow label={t("colChannel")}>{t(`channels.${template.channel}`)}</DetailRow>
              <DetailRow label={t("colLocale")}>{template.locale.toUpperCase()}</DetailRow>
              <DetailRow label={t("colVersion")}>v{template.version}</DetailRow>
              <DetailRow label={t("colActivated")}>
                {template.activated_at ? formatDateTime(template.activated_at, locale) : t("neverActivated")}
              </DetailRow>
            </dl>
          </DetailSheetSection>

          <DetailSheetSection title={t("contentSection")}>
            {template.subject && (
              <div className="mb-3">
                <p className="type-caption font-semibold uppercase tracking-[0.04em] text-muted-foreground">
                  <Mail aria-hidden className="mr-1 inline size-3.5" strokeWidth={1.8} />
                  {t("subject")}
                </p>
                <p className="mt-0.5 text-[0.8125rem] text-foreground">{template.subject}</p>
              </div>
            )}
            {template.title && (
              <div className="mb-3">
                <p className="type-caption font-semibold uppercase tracking-[0.04em] text-muted-foreground">{t("titleField")}</p>
                <p className="mt-0.5 text-[0.8125rem] text-foreground">{template.title}</p>
              </div>
            )}
            <p className="type-caption font-semibold uppercase tracking-[0.04em] text-muted-foreground">{t("body")}</p>
            <pre className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-[var(--bg-subtle)] p-3 font-sans text-[0.8125rem] text-foreground">
              {template.body}
            </pre>
          </DetailSheetSection>

          <DetailSheetSection title={t("variablesSection")}>
            <div className="mb-3">
              <p className="type-caption font-semibold uppercase tracking-[0.04em] text-muted-foreground">{t("allowedVars")}</p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {allowed.length > 0 ? (
                  allowed.map((v) => (
                    <StatusChip key={v} tone="neutral" size="sm" className="font-mono">
                      {v}
                    </StatusChip>
                  ))
                ) : (
                  <span className="type-small text-muted-foreground">—</span>
                )}
              </div>
            </div>
            <div>
              <p className="type-caption font-semibold uppercase tracking-[0.04em] text-muted-foreground">{t("requiredVars")}</p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {required.length > 0 ? (
                  required.map((v) => (
                    <StatusChip key={v} tone="amber" size="sm" className="font-mono">
                      {v}
                    </StatusChip>
                  ))
                ) : (
                  <span className="type-small text-muted-foreground">—</span>
                )}
              </div>
            </div>
          </DetailSheetSection>
        </>
      )}
    </DetailSheet>
  );
}

function PreviewField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="type-caption font-semibold uppercase tracking-[0.04em] text-muted-foreground">{label}</p>
      <div className="mt-0.5 text-[0.8125rem] text-foreground">{children}</div>
    </div>
  );
}

function describeTemplateError(error: unknown, fallback: (e: unknown) => string): string {
  if (error instanceof ApiError) {
    const unknownVars = error.details?.unknown_variables;
    if (Array.isArray(unknownVars) && unknownVars.length > 0) {
      return `Unknown variables: ${unknownVars.join(", ")}`;
    }
    const missingVars = error.details?.missing_variables;
    if (Array.isArray(missingVars) && missingVars.length > 0) {
      return `Missing required variables: ${missingVars.join(", ")}`;
    }
  }
  return fallback(error);
}
