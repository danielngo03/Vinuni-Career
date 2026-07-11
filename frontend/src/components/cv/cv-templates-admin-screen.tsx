"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  FileText,
  LayoutTemplate,
  Layers,
  Pencil,
  Plus,
  ShieldCheck,
} from "lucide-react";
import { Button, Input, Modal, Switch, Textarea, useToast } from "@/components/ui";
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
import { cn } from "@/lib/utils";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import {
  ApiError,
  cvApi,
  type AdminCvTemplateCreateBody,
  type AdminCvTemplateUpdateBody,
  type CvTemplate,
} from "@/lib/api";

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
    ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];
}

function displayName(template: CvTemplate, locale: string): string {
  return locale === "en"
    ? (template.name_en ?? template.name)
    : (template.name_vi ?? template.name);
}

/* -------------------------------------------------------------------------- */
/* Screen                                                                       */
/* -------------------------------------------------------------------------- */

export function CvTemplatesAdminScreen() {
  const t = useTranslations("cvTemplatesAdmin");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const toast = useToast();
  const getErrorMessage = useApiErrorMessage();
  const qc = useQueryClient();

  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [editing, setEditing] = React.useState<CvTemplate | null>(null);
  const [form, setForm] = React.useState<TemplateForm>(EMPTY_FORM);
  const [formOpen, setFormOpen] = React.useState(false);
  const [jsonError, setJsonError] = React.useState<string | null>(null);
  const [search, setSearch] = React.useState("");
  const [category, setCategory] = React.useState("all");

  const query = useQuery({
    queryKey: ["admin", "cv-templates"],
    queryFn: () => cvApi.listAdminTemplates(),
    retry: false,
  });

  const templates = React.useMemo(() => query.data ?? [], [query.data]);

  const categories = React.useMemo(
    () => Array.from(new Set(templates.map((x) => x.category))).sort(),
    [templates],
  );

  const filtered = React.useMemo(() => {
    return templates.filter((x) => {
      if (category !== "all" && x.category !== category) return false;
      const q = search.trim().toLowerCase();
      if (!q) return true;
      return (
        x.key.toLowerCase().includes(q) ||
        displayName(x, locale).toLowerCase().includes(q) ||
        x.category.toLowerCase().includes(q)
      );
    });
  }, [templates, category, search, locale]);

  const stats = React.useMemo(() => {
    const active = templates.filter((item) => item.is_active !== false).length;
    return { active, categories: categories.length };
  }, [templates, categories]);

  const selected = React.useMemo(
    () => templates.find((x) => x.id === selectedId) ?? null,
    [templates, selectedId],
  );

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["admin", "cv-templates"] });
    void qc.invalidateQueries({ queryKey: ["cv", "templates"] });
  }

  function closeForm() {
    setFormOpen(false);
    setEditing(null);
    setForm(EMPTY_FORM);
    setJsonError(null);
  }

  function openCreate() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setJsonError(null);
    setFormOpen(true);
  }

  function openEdit(template: CvTemplate) {
    setEditing(template);
    setForm(formFromTemplate(template));
    setJsonError(null);
    setFormOpen(true);
  }

  function buildBody(): AdminCvTemplateCreateBody | AdminCvTemplateUpdateBody {
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
  }

  const create = useMutation({
    mutationFn: () => cvApi.createTemplate(buildBody() as AdminCvTemplateCreateBody),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("createdToast") });
      closeForm();
      refresh();
    },
    onError: (error) => {
      if ((error as Error).message === "invalid_json") return;
      toast.show({ tone: "error", title: getErrorMessage(error) });
    },
  });

  const update = useMutation({
    mutationFn: () => {
      if (!editing) throw new Error("missing_template");
      return cvApi.updateTemplate(editing.id, buildBody());
    },
    onSuccess: () => {
      toast.show({ tone: "success", title: t("updatedToast") });
      closeForm();
      refresh();
    },
    onError: (error) => {
      if ((error as Error).message === "invalid_json") return;
      toast.show({ tone: "error", title: getErrorMessage(error) });
    },
  });

  const togglePublish = useMutation({
    mutationFn: (template: CvTemplate) =>
      cvApi.updateTemplate(template.id, { is_active: !(template.is_active ?? true) }),
    onSuccess: (updated) => {
      toast.show({
        tone: "success",
        title: updated.is_active === false ? t("unpublishedToast") : t("publishedToast"),
      });
      refresh();
    },
    onError: (error) => toast.show({ tone: "error", title: getErrorMessage(error) }),
  });

  const header = (
    <PageHeader
      title={t("title")}
      subtitle={t("subtitle")}
      actions={
        <Button variant="primary" size="sm" onClick={openCreate}>
          <Plus className="size-4" strokeWidth={2} />
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

  const columns: ColumnDef<CvTemplate, unknown>[] = [
    {
      accessorKey: "name",
      header: t("colName"),
      cell: ({ row }) => (
        <div className="min-w-0">
          <span className="block truncate font-semibold text-foreground">{displayName(row.original, locale)}</span>
          <span className="type-caption block truncate font-mono text-muted-foreground">{row.original.key}</span>
        </div>
      ),
    },
    {
      accessorKey: "category",
      header: t("colCategory"),
      cell: ({ row }) => (
        <StatusChip tone="indigo" size="sm">
          {row.original.category}
        </StatusChip>
      ),
    },
    {
      accessorKey: "is_active",
      header: t("colStatus"),
      cell: ({ row }) => {
        const active = row.original.is_active !== false;
        return (
          <StatusChip tone={active ? "success" : "neutral"} dot size="sm">
            {active ? t("active") : t("inactive")}
          </StatusChip>
        );
      },
    },
    {
      id: "sections",
      header: t("colSections"),
      enableSorting: false,
      meta: { align: "right" },
      cell: ({ row }) => {
        const count = splitList(
          row.original.layout_schema?.order ?? row.original.layout_schema?.section_order,
        ).length;
        return <span className="tabular-nums text-muted-foreground">{count || "—"}</span>;
      },
    },
    {
      id: "actions",
      header: "",
      enableSorting: false,
      meta: { align: "right" },
      cell: ({ row }) => (
        <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
          <Button variant="ghost" size="sm" onClick={() => openEdit(row.original)}>
            <Pencil className="size-4" strokeWidth={1.8} />
            {t("edit")}
          </Button>
        </div>
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
          <KpiTile label={t("total")} value={String(templates.length)} icon={LayoutTemplate} />
          <KpiTile label={t("activeMetric")} value={String(stats.active)} icon={ShieldCheck} />
          <KpiTile label={t("categoryCount")} value={String(stats.categories)} icon={Layers} />
        </KpiRow>

        <FilterBar
          search={{
            value: search,
            onChange: setSearch,
            placeholder: t("searchPlaceholder"),
            ariaLabel: t("searchPlaceholder"),
          }}
        >
          <div className="flex flex-wrap gap-1.5" role="group" aria-label={t("filterCategory")}>
            {["all", ...categories].map((c) => {
              const active = category === c;
              return (
                <button
                  key={c}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setCategory(c)}
                  className={cn(
                    "inline-flex items-center rounded-full border px-3 py-1 text-[0.8125rem] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]",
                    active
                      ? "border-transparent bg-foreground text-[var(--surface-card)]"
                      : "border-border bg-card text-muted-foreground hover:text-foreground",
                  )}
                >
                  {c === "all" ? t("filterAllCategories") : c}
                </button>
              );
            })}
          </div>
        </FilterBar>

        {loadError ? (
          <EmptyState
            kind="error"
            title={t("loadFailed")}
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
                data={filtered}
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
                        <Plus className="size-4" strokeWidth={2} />
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

      {/* Detail sheet */}
      <TemplateDetailSheet
        template={selected}
        locale={locale}
        onClose={() => setSelectedId(null)}
        onEdit={(tpl) => {
          setSelectedId(null);
          openEdit(tpl);
        }}
        onTogglePublish={(tpl) => togglePublish.mutate(tpl)}
        toggling={togglePublish.isPending}
      />

      {/* Create / edit modal */}
      <Modal
        open={formOpen}
        onClose={closeForm}
        title={editing ? t("editTitle") : t("createTitle")}
        description={t("formHint")}
        size="lg"
        footer={
          <>
            <Button variant="ghost" onClick={closeForm} disabled={create.isPending || update.isPending}>
              {t("cancel")}
            </Button>
            <Button
              loading={create.isPending || update.isPending}
              onClick={() => (editing ? update.mutate() : create.mutate())}
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
            disabled={!!editing}
            value={form.key}
            onChange={(e) => setForm((prev) => ({ ...prev, key: e.target.value }))}
            help={t("keyHelp")}
          />
          <Input
            label={t("category")}
            required
            value={form.category}
            onChange={(e) => setForm((prev) => ({ ...prev, category: e.target.value }))}
          />
          <Input
            label={t("nameVi")}
            required
            value={form.nameVi}
            onChange={(e) => setForm((prev) => ({ ...prev, nameVi: e.target.value }))}
          />
          <Input
            label={t("nameEn")}
            required
            value={form.nameEn}
            onChange={(e) => setForm((prev) => ({ ...prev, nameEn: e.target.value }))}
          />
        </div>
        <div className="mt-4 flex flex-wrap gap-4">
          <Switch
            label={t("isActive")}
            checked={form.isActive}
            onCheckedChange={(checked) => setForm((prev) => ({ ...prev, isActive: checked }))}
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
          onChange={(e) => setForm((prev) => ({ ...prev, layoutSchemaText: e.target.value }))}
        />
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
  onTogglePublish,
  toggling,
}: {
  template: CvTemplate | null;
  locale: string;
  onClose: () => void;
  onEdit: (template: CvTemplate) => void;
  onTogglePublish: (template: CvTemplate) => void;
  toggling: boolean;
}) {
  const t = useTranslations("cvTemplatesAdmin");
  const tc = useTranslations("common");
  const open = template != null;
  const schema = template?.layout_schema;
  const active = template ? template.is_active !== false : false;

  const sections = splitList(schema?.order ?? schema?.section_order);
  const roles = splitList(schema?.target_roles);
  const strengths = splitList(schema?.strengths);
  const pageSize = schema?.page?.size;
  const maxPages = schema?.page?.max_pages;
  const font = schema?.typography?.font;

  return (
    <DetailSheet
      open={open}
      onClose={onClose}
      title={template ? displayName(template, locale) : ""}
      subtitle={template ? template.key : undefined}
      status={
        template ? (
          <>
            <StatusChip tone={active ? "success" : "neutral"} dot>
              {active ? t("active") : t("inactive")}
            </StatusChip>
            <StatusChip tone="indigo">{template.category}</StatusChip>
          </>
        ) : undefined
      }
      width="lg"
      closeLabel={tc("close")}
      footer={
        template ? (
          <>
            <Button
              variant="secondary"
              size="sm"
              loading={toggling}
              onClick={() => onTogglePublish(template)}
            >
              {active ? t("unpublish") : t("publish")}
            </Button>
            <Button variant="primary" size="sm" onClick={() => onEdit(template)}>
              <Pencil className="size-4" strokeWidth={1.8} />
              {t("edit")}
            </Button>
          </>
        ) : undefined
      }
    >
      {template && (
        <>
          <DetailSheetSection title={t("previewSection")}>
            {template.preview_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={template.preview_url}
                alt={displayName(template, locale)}
                className="w-full rounded-lg border border-border"
              />
            ) : (
              <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border bg-[var(--bg-subtle)] py-10 text-center">
                <FileText className="size-6 text-muted-foreground" strokeWidth={1.6} />
                <p className="type-small text-muted-foreground">{t("noPreview")}</p>
              </div>
            )}
          </DetailSheetSection>

          <DetailSheetSection title={t("schemaSection")}>
            <ChipList label={t("sections")} items={sections} />
            <ChipList label={t("targetRoles")} items={roles} />
            <ChipList label={t("strengths")} items={strengths} />
          </DetailSheetSection>

          <DetailSheetSection title={t("metaSection")}>
            <dl>
              <DetailRow label={t("pageLabel")}>
                {pageSize ? `${pageSize}${maxPages ? ` · ${maxPages}p` : ""}` : "—"}
              </DetailRow>
              <DetailRow label={t("typographyLabel")}>{font ?? "—"}</DetailRow>
              <DetailRow label={t("colStatus")}>{active ? t("active") : t("inactive")}</DetailRow>
            </dl>
            <p className="mt-3 type-caption text-muted-foreground">{t("versioningNote")}</p>
          </DetailSheetSection>
        </>
      )}
    </DetailSheet>
  );
}

function ChipList({ label, items }: { label: string; items: string[] }) {
  const chip: ChipTone = "neutral";
  return (
    <div className="mb-3 last:mb-0">
      <p className="type-caption font-semibold uppercase tracking-[0.04em] text-muted-foreground">{label}</p>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {items.length > 0 ? (
          items.slice(0, 8).map((item) => (
            <StatusChip key={item} tone={chip} size="sm">
              {item}
            </StatusChip>
          ))
        ) : (
          <span className="type-small text-muted-foreground">—</span>
        )}
      </div>
    </div>
  );
}
