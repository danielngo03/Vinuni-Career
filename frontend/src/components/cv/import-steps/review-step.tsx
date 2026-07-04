"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import {
  Check,
  CheckCircle,
  FilePlus,
  Info,
  Translate,
  Warning,
  X,
} from "@phosphor-icons/react";
import { Button, Input, Select, Tabs, Textarea } from "@/components/ui";
import { CvOriginalPreview } from "../cv-original-preview";
import { cn } from "@/lib/utils";
import { cvApi } from "@/lib/api";
import type { CvTemplate, Ingestion, ImportIngestionBody, UploadPreview } from "@/lib/api";
import {
  buildOverrides,
  buildRows,
  initialDecisions,
  initialValues,
  pendingCount as countPending,
  type FieldDecision,
  type FieldRow,
} from "@/lib/cv/review-fields";

/**
 * The real review screen (``docs/CV_INGESTION_EXTRACTION_SPEC.md`` §2 "Review
 * Screen"): original document preview beside the extracted, per-field editable
 * data. Nothing is imported until the student presses "Import to CV" — editing
 * or explicitly confirming/removing every "Check this" field first.
 */
export function ReviewStep({
  ingestion,
  preview,
  titleDraft,
  onTitleChange,
  onImport,
  onKeepOriginal,
  onUploadAnother,
  importing,
  forcePendingPaths,
}: {
  ingestion: Ingestion;
  preview: UploadPreview;
  titleDraft: string;
  onTitleChange: (title: string) => void;
  onImport: (body: ImportIngestionBody) => void;
  onKeepOriginal: () => void;
  onUploadAnother: () => void;
  importing: boolean;
  /**
   * Paths the backend's per-field confirmation gate (422
   * `fact_confirmation_required`) rejected as undecided — re-marks those rows
   * "pending" even if the student had locally accepted them, so the highlighted
   * set always matches what the server will actually enforce.
   */
  forcePendingPaths?: string[];
}) {
  const t = useTranslations("cv.import");
  const tGroup = useTranslations("cv.import.group");
  const tField = useTranslations("cv.import");

  const rows = useMemo(() => buildRows(ingestion.review_fields), [ingestion.review_fields]);

  const [values, setValues] = useState<Record<string, string>>(() => initialValues(rows));
  const [decisions, setDecisions] = useState<Record<string, FieldDecision>>(() =>
    initialDecisions(rows),
  );
  const [templates, setTemplates] = useState<CvTemplate[]>([]);
  const [templateId, setTemplateId] = useState<string>("");
  const [mobileTab, setMobileTab] = useState<"original" | "review" | "template">("review");

  useEffect(() => {
    let cancelled = false;
    cvApi
      .listTemplates()
      .then((list) => {
        if (!cancelled) setTemplates(list);
      })
      .catch(() => {
        /* template gallery is optional here; import still works without one */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!forcePendingPaths || forcePendingPaths.length === 0) return;
    const targets = new Set(forcePendingPaths);
    setDecisions((prev) => {
      const next = { ...prev };
      for (const path of targets) {
        if (path in next) next[path] = "pending";
      }
      return next;
    });
  }, [forcePendingPaths]);

  const pendingCount = countPending(rows, decisions);
  const needsReviewRows = rows.filter((r) => r.needs_review);
  const hasNeedsReviewFields = needsReviewRows.length > 0;
  const canImport = pendingCount === 0 && !importing;

  function setValue(path: string, value: string) {
    setValues((prev) => ({ ...prev, [path]: value }));
    setDecisions((prev) =>
      prev[path] === "pending" ? { ...prev, [path]: "accepted" } : prev,
    );
  }

  function confirmField(path: string) {
    setDecisions((prev) => ({ ...prev, [path]: "accepted" }));
  }

  function removeField(path: string) {
    setDecisions((prev) => ({ ...prev, [path]: "rejected" }));
  }

  function fieldLabel(row: FieldRow): string {
    if (row.fieldKey && tField.has(row.fieldKey)) return tField(row.fieldKey);
    const groupLabel = tGroup.has(row.group) ? tGroup(row.group) : tGroup("other");
    return row.indexInGroup ? `${groupLabel} ${row.indexInGroup}` : groupLabel;
  }

  function groupLabel(group: string): string {
    return tGroup.has(group) ? tGroup(group) : tGroup("other");
  }

  const groups = useMemo(() => {
    const order: string[] = [];
    const byGroup = new Map<string, FieldRow[]>();
    for (const row of rows) {
      if (!byGroup.has(row.group)) {
        byGroup.set(row.group, []);
        order.push(row.group);
      }
      byGroup.get(row.group)!.push(row);
    }
    return order.map((g) => ({ group: g, rows: byGroup.get(g)! }));
  }, [rows]);

  function handleImport() {
    const overrides = buildOverrides(rows, values, decisions);
    onImport({
      title: titleDraft.trim() || preview.filename,
      template_id: templateId || null,
      overrides,
      // Fallback for the (rare) needs_review status with no listed fields —
      // never block import on a decision the UI cannot present.
      fact_confirmation: !hasNeedsReviewFields,
    });
  }

  const originalPane = (
    <div className="min-h-[420px] overflow-hidden rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] backdrop-blur-md shadow-[var(--shadow-sm)]">
      <CvOriginalPreview preview={preview} className="h-full" />
    </div>
  );

  const reviewPane = (
    <div className="min-h-[420px] rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] backdrop-blur-md p-4 shadow-[var(--shadow-sm)]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-bold text-[var(--text-primary)]">
            {hasNeedsReviewFields ? t("reviewNeededTitle") : t("readyTitle")}
          </h2>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            {hasNeedsReviewFields ? t("reviewNeededBody") : t("readyBody")}
          </p>
        </div>
        {hasNeedsReviewFields && (
          <span
            className={cn(
              "shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold",
              pendingCount > 0
                ? "bg-[var(--amber-100)] text-[var(--amber-700)]"
                : "bg-[var(--green-100)] text-[var(--green-700)]",
            )}
          >
            {pendingCount > 0 ? t("checkCount", { count: pendingCount }) : t("allClear")}
          </span>
        )}
      </div>

      {ingestion.mixed_language && (
        <div className="mt-3 flex items-start gap-2 rounded-lg bg-[var(--amber-100)] p-2.5 text-xs text-[var(--amber-700)]">
          <Translate aria-hidden weight="duotone" className="mt-px size-3.5 shrink-0" />
          {t("mixedLanguage")}
        </div>
      )}

      {rows.length === 0 ? (
        <div className="mt-4 rounded-lg border border-dashed border-[var(--glass-border-strong)] p-4 text-center">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            {t("noFieldsTitle")}
          </p>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">{t("noFieldsBody")}</p>
        </div>
      ) : (
        <div className="mt-4 space-y-5">
          {groups.map(({ group, rows: groupRows }) => (
            <div key={group}>
              <h3 className="text-xs font-bold uppercase tracking-wide text-[var(--text-muted)]">
                {groupLabel(group)}
              </h3>
              <div className="mt-2 space-y-3">
                {groupRows.map((row) => {
                  const decision = decisions[row.path] ?? "accepted";
                  if (decision === "rejected") {
                    return (
                      <div
                        key={row.path}
                        className="flex items-center justify-between gap-2 rounded-lg border border-dashed border-[var(--glass-border-strong)] p-2.5 text-xs text-[var(--text-muted)]"
                      >
                        <span className="truncate">{fieldLabel(row)} — {t("removedFromImport")}</span>
                        <Button variant="ghost" size="sm" onClick={() => confirmField(row.path)}>
                          {t("undoRemove")}
                        </Button>
                      </div>
                    );
                  }
                  const long = (values[row.path] ?? "").length > 80;
                  return (
                    <div key={row.path}>
                      <div className="mb-1 flex items-center justify-between gap-2">
                        <label
                          htmlFor={`review-field-${row.path}`}
                          className="flex items-center gap-1.5 text-xs font-semibold text-[var(--text-primary)]"
                        >
                          {fieldLabel(row)}
                          {row.needs_review && (
                            <span
                              className={cn(
                                "inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-bold",
                                decision === "pending"
                                  ? "bg-[var(--amber-100)] text-[var(--amber-700)]"
                                  : "bg-[var(--green-100)] text-[var(--green-700)]",
                              )}
                            >
                              {decision === "pending" ? (
                                <Warning aria-hidden weight="fill" className="size-2.5" />
                              ) : (
                                <CheckCircle aria-hidden weight="fill" className="size-2.5" />
                              )}
                              {t("checkThis")}
                            </span>
                          )}
                        </label>
                        {row.page ? (
                          <span className="shrink-0 text-[10px] text-[var(--text-muted)]">
                            {t("fromPage", { page: row.page })}
                          </span>
                        ) : null}
                      </div>
                      {long ? (
                        <Textarea
                          id={`review-field-${row.path}`}
                          value={values[row.path] ?? ""}
                          onChange={(e) => setValue(row.path, e.target.value)}
                          rows={3}
                          className={row.needs_review && decision === "pending" ? "ring-2 ring-[var(--amber-400)]" : ""}
                        />
                      ) : (
                        <Input
                          id={`review-field-${row.path}`}
                          value={values[row.path] ?? ""}
                          onChange={(e) => setValue(row.path, e.target.value)}
                          className={row.needs_review && decision === "pending" ? "ring-2 ring-[var(--amber-400)]" : ""}
                        />
                      )}
                      {row.needs_review && (
                        <div className="mt-1.5 flex gap-2">
                          <Button variant="ghost" size="sm" onClick={() => confirmField(row.path)}>
                            <Check aria-hidden weight="bold" className="size-3.5" />
                            {t("confirmField")}
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => removeField(row.path)}>
                            <X aria-hidden weight="bold" className="size-3.5" />
                            {t("removeField")}
                          </Button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const importPane = (
    <aside className="lg:sticky lg:top-4">
      <div className="rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] backdrop-blur-md p-4 shadow-[var(--shadow-sm)]">
        <h2 className="text-sm font-bold text-[var(--text-primary)]">
          {t("importPanelTitle")}
        </h2>
        <div className="mt-3 space-y-3">
          <Input
            label={t("titleFieldLabel")}
            placeholder={t("titlePlaceholder")}
            value={titleDraft}
            onChange={(e) => onTitleChange(e.target.value)}
          />
          <Select
            label={t("templateFieldLabel")}
            value={templateId}
            onChange={(e) => setTemplateId(e.target.value)}
            options={[
              { value: "", label: t("templateNone") },
              ...templates.map((tpl) => ({ value: tpl.id, label: tpl.name })),
            ]}
          />
        </div>

        {pendingCount > 0 && (
          <p className="mt-3 flex items-start gap-1.5 text-xs text-[var(--amber-700)]">
            <Warning aria-hidden weight="duotone" className="mt-px size-3.5 shrink-0" />
            {t("confirmFactsNote")}
          </p>
        )}

        <div className="mt-4 flex flex-col gap-2">
          <Button
            variant="primary"
            fullWidth
            disabled={!canImport}
            onClick={handleImport}
          >
            {importing ? t("importing") : t("importToCv")}
          </Button>
          <Button variant="secondary" fullWidth onClick={onKeepOriginal} disabled={importing}>
            {t("keepOriginal")}
          </Button>
          <Button variant="ghost" fullWidth onClick={onUploadAnother} disabled={importing}>
            <FilePlus aria-hidden weight="bold" className="size-4" />
            {t("uploadAnother")}
          </Button>
        </div>

        <p className="mt-3 flex items-start gap-1.5 text-[11px] leading-relaxed text-[var(--text-muted)]">
          <Info aria-hidden weight="duotone" className="mt-px size-3.5 shrink-0" />
          {t("importDraftNote")}
        </p>
      </div>
    </aside>
  );

  return (
    <div>
      {/* Desktop: original | fields | actions, three columns per spec §2. */}
      <div className="hidden gap-4 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_300px]">
        {originalPane}
        {reviewPane}
        {importPane}
      </div>

      {/* Mobile: tabbed Original | Review | Template, sticky actions. */}
      <div className="lg:hidden">
        <Tabs
          ariaLabel={t("tabsLabel")}
          value={mobileTab}
          onValueChange={(v) => setMobileTab(v as typeof mobileTab)}
          items={[
            { value: "original", label: t("tabOriginal") },
            { value: "review", label: t("tabReview") },
            { value: "template", label: t("tabTemplate") },
          ]}
        />
        <div className="mt-3">
          {mobileTab === "original" && originalPane}
          {mobileTab === "review" && reviewPane}
          {mobileTab === "template" && importPane}
        </div>
      </div>
    </div>
  );
}
