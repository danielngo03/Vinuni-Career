"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  FileText,
  PencilSimple,
  PlusCircle,
  ShieldWarning,
  SignIn,
} from "@phosphor-icons/react";
import {
  Button,
  EmptyState,
  Input,
  Modal,
  SkeletonCard,
  StatusBadge,
  Switch,
  Textarea,
  useToast,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import {
  ApiError,
  cvApi,
  type AdminCvTemplateCreateBody,
  type AdminCvTemplateUpdateBody,
  type CvTemplate,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type TemplateForm = {
  key: string;
  nameVi: string;
  nameEn: string;
  category: string;
  layoutSchemaText: string;
  isActive: boolean;
};

const EMPTY_LAYOUT = {
  section_order: ["summary", "experience", "education", "skills"],
  target_roles: [],
  strengths: [],
  page: { size: "A4", max_pages: 2 },
  typography: { font: "Inter", base_pt: 10 },
};

const EMPTY_FORM: TemplateForm = {
  key: "",
  nameVi: "",
  nameEn: "",
  category: "business",
  layoutSchemaText: JSON.stringify(EMPTY_LAYOUT, null, 2),
  isActive: true,
};

function formFromTemplate(template: CvTemplate): TemplateForm {
  return {
    key: template.key,
    nameVi: template.name_vi ?? template.name,
    nameEn: template.name_en ?? template.name,
    category: template.category,
    layoutSchemaText: JSON.stringify(template.layout_schema ?? EMPTY_LAYOUT, null, 2),
    isActive: template.is_active ?? true,
  };
}

function splitList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter(
        (item): item is string => typeof item === "string" && item.trim().length > 0,
      )
    : [];
}

export function CvTemplatesAdminScreen() {
  const t = useTranslations("cvTemplatesAdmin");
  const tStates = useTranslations("states");
  const locale = useLocale();
  const toast = useToast();
  const getErrorMessage = useApiErrorMessage();
  const qc = useQueryClient();

  const [selected, setSelected] = useState<CvTemplate | null>(null);
  const [form, setForm] = useState<TemplateForm>(EMPTY_FORM);
  const [open, setOpen] = useState(false);
  const [jsonError, setJsonError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["admin", "cv-templates"],
    queryFn: () => cvApi.listAdminTemplates(),
  });

  const templates = useMemo(() => query.data ?? [], [query.data]);

  const stats = useMemo(() => {
    const active = templates.filter((item) => item.is_active !== false).length;
    const categories = new Set(templates.map((item) => item.category)).size;
    return { active, categories };
  }, [templates]);

  const closeDialog = () => {
    setOpen(false);
    setSelected(null);
    setForm(EMPTY_FORM);
    setJsonError(null);
  };

  const openCreate = () => {
    setSelected(null);
    setForm(EMPTY_FORM);
    setJsonError(null);
    setOpen(true);
  };

  const openEdit = (template: CvTemplate) => {
    setSelected(template);
    setForm(formFromTemplate(template));
    setJsonError(null);
    setOpen(true);
  };

  const buildBody = (): AdminCvTemplateCreateBody | AdminCvTemplateUpdateBody => {
    let layoutSchema: Record<string, unknown>;
    try {
      const parsed = JSON.parse(form.layoutSchemaText) as unknown;
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("schema_not_object");
      }
      layoutSchema = parsed as Record<string, unknown>;
    } catch {
      setJsonError(t("jsonInvalid"));
      throw new Error("invalid_json");
    }
    setJsonError(null);

    return {
      key: form.key.trim(),
      name_vi: form.nameVi.trim(),
      name_en: form.nameEn.trim(),
      category: form.category.trim(),
      layout_schema: layoutSchema,
      is_active: form.isActive,
    };
  };

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["admin", "cv-templates"] });
    qc.invalidateQueries({ queryKey: ["cv", "templates"] });
  };

  const create = useMutation({
    mutationFn: () => cvApi.createTemplate(buildBody() as AdminCvTemplateCreateBody),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("createdToast") });
      closeDialog();
      refresh();
    },
    onError: (error) => {
      if ((error as Error).message === "invalid_json") return;
      toast.show({ tone: "error", title: getErrorMessage(error) });
    },
  });

  const update = useMutation({
    mutationFn: () => {
      if (!selected) throw new Error("missing_template");
      return cvApi.updateTemplate(selected.id, buildBody());
    },
    onSuccess: () => {
      toast.show({ tone: "success", title: t("updatedToast") });
      closeDialog();
      refresh();
    },
    onError: (error) => {
      if ((error as Error).message === "invalid_json") return;
      toast.show({ tone: "error", title: getErrorMessage(error) });
    },
  });

  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          <PageHeader title={t("title")} description={t("subtitle")} />
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            icon={err.isPermissionError ? ShieldWarning : SignIn}
            title={
              err.isPermissionError
                ? tStates("permissionTitle")
                : tStates("authTitle")
            }
            description={
              err.isPermissionError ? t("permissionBody") : tStates("authBody")
            }
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
            <PlusCircle aria-hidden weight="bold" className="size-4" />
            {t("create")}
          </Button>
        }
      />

      <div className="mb-5 grid gap-3 md:grid-cols-3">
        <MetricCard label={t("total")} value={String(templates.length)} />
        <MetricCard label={t("activeMetric")} value={String(stats.active)} />
        <MetricCard
          label={t("categoryCount")}
          value={String(stats.categories)}
        />
      </div>

      {query.isLoading ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : query.isError ? (
        <EmptyState
          kind="error"
          icon={ShieldWarning}
          title={t("loadFailed")}
          description={getErrorMessage(query.error)}
        />
      ) : templates.length === 0 ? (
        <EmptyState
          kind="empty"
          icon={FileText}
          title={t("emptyTitle")}
          description={t("emptyBody")}
          action={
            <Button onClick={openCreate}>
              <PlusCircle aria-hidden weight="bold" className="size-4" />
              {t("create")}
            </Button>
          }
        />
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {templates.map((template) => {
            const displayName =
              locale === "en"
                ? (template.name_en ?? template.name)
                : (template.name_vi ?? template.name);
            const roles = splitList(template.layout_schema?.target_roles);
            const strengths = splitList(template.layout_schema?.strengths);
            const sections = splitList(template.layout_schema?.section_order);
            return (
              <article
                key={template.id}
                className={cn(
                  "rounded-xl border bg-white/85 p-4 shadow-sm backdrop-blur",
                  template.is_active === false
                    ? "border-[var(--border-default)] opacity-75"
                    : "border-white/70",
                )}
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <StatusBadge
                        tone={template.is_active === false ? "closed" : "active"}
                      >
                        {template.is_active === false ? t("inactive") : t("active")}
                      </StatusBadge>
                      <StatusBadge tone="info">{template.category}</StatusBadge>
                    </div>
                    <h2 className="truncate text-base font-bold text-[var(--text-primary)]">
                      {displayName}
                    </h2>
                    <p className="mt-1 truncate text-xs font-semibold text-[var(--text-secondary)]">
                      {template.key}
                    </p>
                  </div>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => openEdit(template)}
                  >
                    <PencilSimple aria-hidden weight="bold" className="size-4" />
                    {t("edit")}
                  </Button>
                </div>

                <div className="mt-4 grid gap-3 sm:grid-cols-3">
                  <MiniList title={t("sections")} items={sections} />
                  <MiniList title={t("targetRoles")} items={roles} />
                  <MiniList title={t("strengths")} items={strengths} />
                </div>
              </article>
            );
          })}
        </div>
      )}

      <Modal
        open={open}
        onClose={closeDialog}
        title={selected ? t("editTitle") : t("createTitle")}
        description={t("formHint")}
        size="lg"
        footer={
          <>
            <Button variant="ghost" onClick={closeDialog} disabled={submitting}>
              {t("cancel")}
            </Button>
            <Button
              loading={submitting}
              onClick={() => (selected ? update.mutate() : create.mutate())}
            >
              {t("save")}
            </Button>
          </>
        }
      >
        <div className="grid gap-4 md:grid-cols-2">
          <Input
            label={t("key")}
            required
            value={form.key}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, key: event.target.value }))
            }
            help={t("keyHelp")}
          />
          <Input
            label={t("category")}
            required
            value={form.category}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, category: event.target.value }))
            }
          />
          <Input
            label={t("nameVi")}
            required
            value={form.nameVi}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, nameVi: event.target.value }))
            }
          />
          <Input
            label={t("nameEn")}
            required
            value={form.nameEn}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, nameEn: event.target.value }))
            }
          />
        </div>
        <div className="mt-4 flex flex-wrap gap-4">
          <Switch
            label={t("isActive")}
            checked={form.isActive}
            onCheckedChange={(checked) =>
              setForm((prev) => ({ ...prev, isActive: checked }))
            }
          />
        </div>
        <Textarea
          className="mt-4 font-mono text-xs"
          rows={14}
          label={t("layoutSchema")}
          required
          value={form.layoutSchemaText}
          error={jsonError ?? undefined}
          help={t("layoutHelp")}
          onChange={(event) =>
            setForm((prev) => ({
              ...prev,
              layoutSchemaText: event.target.value,
            }))
          }
        />
      </Modal>
    </>
  );
}

function MetricCard({
  label,
  value,
  helper,
}: {
  label: string;
  value: string;
  helper?: string;
}) {
  return (
    <div className="rounded-xl border border-white/70 bg-white/85 p-4 shadow-sm">
      <p className="text-xs font-semibold uppercase text-[var(--text-secondary)]">
        {label}
      </p>
      <p className="mt-1 text-2xl font-extrabold text-[var(--text-primary)]">
        {value}
      </p>
      {helper && (
        <p className="mt-1 text-xs text-[var(--text-secondary)]">{helper}</p>
      )}
    </div>
  );
}

function MiniList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-lg bg-[var(--bg-subtle)] p-3">
      <p className="text-xs font-bold uppercase text-[var(--text-secondary)]">
        {title}
      </p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {items.length > 0 ? (
          items.slice(0, 5).map((item) => (
            <span
              key={item}
              className="rounded-md bg-white px-2 py-1 text-xs font-semibold text-[var(--text-primary)]"
            >
              {item}
            </span>
          ))
        ) : (
          <span className="text-xs text-[var(--text-muted)]">-</span>
        )}
      </div>
    </div>
  );
}
