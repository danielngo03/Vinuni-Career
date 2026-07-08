"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle,
  Archive,
  Eye,
  FilePlus,
  PencilSimple,
  ShieldWarning,
  SignIn,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import {
  Button,
  EmptyState,
  Input,
  Modal,
  Select,
  StatusBadge,
  Textarea,
  useToast,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
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
import { useLocale } from "next-intl";

const STATUS_TONE: Record<string, "draft" | "active" | "rejected"> = {
  draft: "draft",
  active: "active",
  archived: "rejected",
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
  return {
    key: "",
    channel: "email",
    locale: "vi",
    subject: "",
    title: "",
    body: "",
    allowed: [],
    required: [],
  };
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
  const [draft, setDraft] = useState("");

  function commit() {
    const v = draft.trim();
    if (v && !values.includes(v)) onChange([...values, v]);
    setDraft("");
  }

  return (
    <div>
      <label className="mb-1.5 block text-sm font-semibold text-[var(--text-primary)]">
        {label}
      </label>
      <div className="flex flex-wrap items-center gap-1.5 rounded-xl border border-[var(--border-default)] bg-white/80 px-2.5 py-2">
        {values.map((v) => (
          <span
            key={v}
            className="inline-flex items-center gap-1 rounded-full bg-[var(--bg-subtle)] px-2.5 py-1 font-mono text-xs text-[var(--text-primary)]"
          >
            {v}
            <button
              type="button"
              onClick={() => onChange(values.filter((item) => item !== v))}
              aria-label={`Remove ${v}`}
              className="text-[var(--text-muted)] hover:text-[var(--brand-red)]"
            >
              <X aria-hidden weight="bold" className="size-3" />
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
          className="min-w-[120px] flex-1 bg-transparent text-sm text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
        />
      </div>
      {help && <p className="mt-1 text-xs text-[var(--text-secondary)]">{help}</p>}
    </div>
  );
}

export function NotificationTemplatesAdminScreen() {
  const t = useTranslations("notificationTemplates");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const toast = useToast();
  const qc = useQueryClient();
  const getErrorMessage = useApiErrorMessage();

  const [keyFilter, setKeyFilter] = useState("");
  const [channelFilter, setChannelFilter] = useState("");
  const [localeFilter, setLocaleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const [formOpen, setFormOpen] = useState(false);
  const [selected, setSelected] = useState<NotificationTemplate | null>(null);
  const [asNewVersion, setAsNewVersion] = useState(false);
  const [form, setForm] = useState<TemplateForm>(emptyForm());
  const [formError, setFormError] = useState<string | null>(null);

  const [previewTarget, setPreviewTarget] = useState<NotificationTemplate | null>(null);
  const [sampleVars, setSampleVars] = useState<Record<string, string>>({});
  const [previewResult, setPreviewResult] = useState<NotificationTemplatePreviewResult | null>(
    null,
  );

  const [confirmAction, setConfirmAction] = useState<{
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

  const templates = useMemo(() => query.data ?? [], [query.data]);

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["admin", "notification-templates"] });
  }

  function openCreate() {
    setSelected(null);
    setAsNewVersion(false);
    setForm(emptyForm());
    setFormError(null);
    setFormOpen(true);
  }

  function openEdit(template: NotificationTemplate) {
    setSelected(template);
    setAsNewVersion(false);
    setForm(formFromTemplate(template));
    setFormError(null);
    setFormOpen(true);
  }

  function openNewVersion(template: NotificationTemplate) {
    setSelected(template);
    setAsNewVersion(true);
    setForm(formFromTemplate(template));
    setFormError(null);
    setFormOpen(true);
  }

  const isEditingDraft = selected !== null && !asNewVersion;

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
      if (!selected) throw new Error("missing_template");
      return templateAdminApi.update(selected.id, {
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
    mutationFn: (template: NotificationTemplate) =>
      templateAdminApi.preview(template.id, sampleVars),
    onSuccess: (data) => setPreviewResult(data),
    onError: (e) => toast.show({ tone: "error", title: getErrorMessage(e) }),
  });

  function openPreview(template: NotificationTemplate) {
    setPreviewTarget(template);
    setPreviewResult(null);
    const initial: Record<string, string> = {};
    for (const name of template.variables_schema?.allowed ?? []) {
      initial[name] = `[${name}]`;
    }
    setSampleVars(initial);
  }

  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          <PageHeader title={t("title")} description={t("subtitle")} />
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            icon={err.isPermissionError ? ShieldWarning : SignIn}
            title={err.isPermissionError ? tStates("permissionTitle") : tStates("authTitle")}
            description={err.isPermissionError ? t("permissionBody") : tStates("authBody")}
          />
        </>
      );
    }
  }

  const submitting = create.isPending || update.isPending;

  return (
    <>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          <Button onClick={openCreate}>
            <FilePlus aria-hidden weight="bold" className="size-4" />
            {t("create")}
          </Button>
        }
      />

      {/* Filters */}
      <div className="mb-5 grid gap-3 sm:grid-cols-4">
        <Input
          label={t("filterKey")}
          value={keyFilter}
          onChange={(e) => setKeyFilter(e.target.value)}
          placeholder={t("filterKeyPlaceholder")}
        />
        <Select
          label={t("filterChannel")}
          value={channelFilter}
          onChange={(e) => setChannelFilter(e.target.value)}
          options={[
            { value: "", label: t("filterAll") },
            ...NOTIFICATION_TEMPLATE_CHANNELS.map((c) => ({ value: c, label: t(`channels.${c}`) })),
          ]}
        />
        <Select
          label={t("filterLocale")}
          value={localeFilter}
          onChange={(e) => setLocaleFilter(e.target.value)}
          options={[
            { value: "", label: t("filterAll") },
            ...NOTIFICATION_TEMPLATE_LOCALES.map((l) => ({ value: l, label: l.toUpperCase() })),
          ]}
        />
        <Select
          label={t("filterStatus")}
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          options={[
            { value: "", label: t("filterAll") },
            ...NOTIFICATION_TEMPLATE_STATUSES.map((s) => ({ value: s, label: t(`statuses.${s}`) })),
          ]}
        />
      </div>

      {query.isPending ? (
        <div className="grid gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl bg-[var(--bg-subtle)]" />
          ))}
        </div>
      ) : query.isError ? (
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={tStates("errorTitle")}
          description={tStates("errorBody")}
          action={
            <Button variant="secondary" onClick={() => query.refetch()}>
              {tc("retry")}
            </Button>
          }
        />
      ) : templates.length === 0 ? (
        <EmptyState
          kind="empty"
          icon={FilePlus}
          title={t("emptyTitle")}
          description={t("emptyBody")}
          action={
            <Button onClick={openCreate}>
              <FilePlus aria-hidden weight="bold" className="size-4" />
              {t("create")}
            </Button>
          }
        />
      ) : (
        <ul className="space-y-3">
          {templates.map((template) => (
            <li
              key={template.id}
              className="rounded-xl border border-[var(--border-default)] bg-white/85 p-4 shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="mb-1.5 flex flex-wrap items-center gap-2">
                    <StatusBadge tone={STATUS_TONE[template.status] ?? "info"}>
                      {t(`statuses.${template.status}`)}
                    </StatusBadge>
                    <StatusBadge tone="info">{t(`channels.${template.channel}`)}</StatusBadge>
                    <span className="text-xs font-semibold uppercase text-[var(--text-muted)]">
                      {template.locale}
                    </span>
                    <span className="text-xs text-[var(--text-muted)]">
                      {t("versionLabel", { version: template.version })}
                    </span>
                  </div>
                  <p className="truncate font-mono text-sm font-bold text-[var(--text-primary)]">
                    {template.key}
                  </p>
                  {template.subject && (
                    <p className="mt-1 truncate text-xs text-[var(--text-secondary)]">
                      {template.subject}
                    </p>
                  )}
                  <p className="mt-1 text-xs text-[var(--text-muted)]">
                    {template.activated_at
                      ? t("activatedAt", { when: formatDateTime(template.activated_at, locale) })
                      : t("neverActivated")}
                  </p>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <Button variant="ghost" size="sm" onClick={() => openPreview(template)}>
                    <Eye aria-hidden weight="bold" className="size-4" />
                    {t("preview")}
                  </Button>
                  {template.status === "draft" && (
                    <Button variant="secondary" size="sm" onClick={() => openEdit(template)}>
                      <PencilSimple aria-hidden weight="bold" className="size-4" />
                      {t("edit")}
                    </Button>
                  )}
                  {template.status !== "active" && (
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => setConfirmAction({ kind: "activate", template })}
                    >
                      <CheckCircle aria-hidden weight="bold" className="size-4" />
                      {t("activate")}
                    </Button>
                  )}
                  {template.status !== "archived" && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setConfirmAction({ kind: "archive", template })}
                    >
                      <Archive aria-hidden weight="bold" className="size-4" />
                      {t("archive")}
                    </Button>
                  )}
                  <Button variant="ghost" size="sm" onClick={() => openNewVersion(template)}>
                    <FilePlus aria-hidden weight="bold" className="size-4" />
                    {t("newVersion")}
                  </Button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* Create / edit draft */}
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
            <Button
              loading={submitting}
              onClick={() => (isEditingDraft ? update.mutate() : create.mutate())}
            >
              {tc("save")}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {formError && (
            <p
              role="alert"
              className="rounded-lg border border-[var(--red-400)]/40 bg-[var(--red-50)] px-3 py-2 text-xs font-medium text-[var(--brand-red)]"
            >
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
              options={NOTIFICATION_TEMPLATE_CHANNELS.map((c) => ({
                value: c,
                label: t(`channels.${c}`),
              }))}
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

      {/* Preview panel */}
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
            <Button
              variant="primary"
              loading={preview.isPending}
              onClick={() => previewTarget && preview.mutate(previewTarget)}
            >
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
                    onChange={(e) =>
                      setSampleVars((prev) => ({ ...prev, [name]: e.target.value }))
                    }
                  />
                ))}
              </div>
            )}
            {previewResult ? (
              <div className="space-y-3 rounded-xl border border-[var(--border-default)] bg-white p-4">
                {previewResult.subject && (
                  <Field label={t("subject")}>{previewResult.subject}</Field>
                )}
                {previewResult.title && <Field label={t("titleField")}>{previewResult.title}</Field>}
                <Field label={t("body")}>
                  <span className="whitespace-pre-wrap">{previewResult.body}</span>
                </Field>
                {previewResult.required_variables.length > 0 && (
                  <Field label={t("requiredVars")}>
                    {previewResult.required_variables.join(", ")}
                  </Field>
                )}
              </div>
            ) : (
              <p className="text-sm text-[var(--text-secondary)]">{t("previewHint")}</p>
            )}
          </div>
        )}
      </Modal>

      {/* Activate / archive confirm */}
      <Modal
        open={confirmAction !== null}
        onClose={() => setConfirmAction(null)}
        title={
          confirmAction?.kind === "activate" ? t("activateConfirmTitle") : t("archiveConfirmTitle")
        }
        description={
          confirmAction?.kind === "activate"
            ? t("activateConfirmBody")
            : t("archiveConfirmBody")
        }
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
        <p className="text-sm text-[var(--text-secondary)]">
          {confirmAction?.template.key} · v{confirmAction?.template.version}
        </p>
      </Modal>
    </>
  );
}

function describeTemplateError(
  error: unknown,
  fallback: (e: unknown) => string,
): string {
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {label}
      </p>
      <div className="mt-0.5 text-sm text-[var(--text-primary)]">{children}</div>
    </div>
  );
}
