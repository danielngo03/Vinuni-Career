"use client";

import * as React from "react";
import { ArrowRight, Download, FileText } from "lucide-react";
import type { CompanyChangeField, CompanyDocument } from "@/lib/api";

/** Human byte size (safe on unknown/0). */
function formatBytes(bytes: number): string {
  if (!bytes || bytes < 1024) return `${bytes || 0} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[i]}`;
}

function fieldValue(v: string | number | null, emptyLabel: string): string {
  if (v === null || v === undefined || v === "") return emptyLabel;
  return String(v);
}

/**
 * A safe list of company documents. Each opens/downloads via a short-lived
 * signed `url` (the backend never returns a storage key). Never reconstruct a
 * path client-side.
 */
export function CompanyDocumentList({
  documents,
  emptyLabel,
  viewLabel,
}: {
  documents: CompanyDocument[];
  emptyLabel: string;
  viewLabel: string;
}) {
  if (documents.length === 0) {
    return <p className="type-small text-muted-foreground">{emptyLabel}</p>;
  }
  return (
    <ul className="space-y-2">
      {documents.map((doc) => (
        <li
          key={doc.id}
          className="flex items-center justify-between gap-3 rounded-lg border border-border bg-[var(--bg-subtle)] px-3 py-2"
        >
          <div className="flex min-w-0 items-center gap-2.5">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-[var(--viz-sky-soft)]">
              <FileText aria-hidden className="size-4 text-[var(--viz-sky)]" strokeWidth={1.8} />
            </span>
            <div className="min-w-0">
              <p className="truncate text-[0.8125rem] font-medium text-foreground">{doc.filename}</p>
              <p className="truncate type-caption text-muted-foreground">
                {[doc.kind_label, formatBytes(doc.size)].filter(Boolean).join(" · ")}
              </p>
            </div>
          </div>
          <a
            href={doc.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-[0.8125rem] font-medium text-foreground outline-none transition-colors hover:bg-[var(--bg-muted)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
          >
            <Download aria-hidden className="size-4" strokeWidth={1.8} />
            {viewLabel}
          </a>
        </li>
      ))}
    </ul>
  );
}

/**
 * A proposed sensitive-field diff — old value struck through, new value bold.
 * Field labels are backend-rendered (never a raw column code).
 */
export function CompanyChangeDiff({
  changes,
  emptyValueLabel,
  emptyLabel,
}: {
  changes: CompanyChangeField[];
  /** Rendered when a from/to value is null/blank. */
  emptyValueLabel: string;
  /** Rendered when the request carries no field changes (documents-only). */
  emptyLabel?: string;
}) {
  if (changes.length === 0) {
    return emptyLabel ? <p className="type-small text-muted-foreground">{emptyLabel}</p> : null;
  }
  return (
    <ul className="space-y-2.5">
      {changes.map((change) => (
        <li
          key={change.field}
          className="rounded-lg border border-border bg-[var(--bg-subtle)] px-3 py-2.5"
        >
          <p className="type-caption font-semibold uppercase tracking-[0.06em] text-muted-foreground">
            {change.label}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[0.8125rem]">
            <span className="text-muted-foreground line-through">
              {fieldValue(change.from, emptyValueLabel)}
            </span>
            <ArrowRight aria-hidden className="size-3.5 shrink-0 text-muted-foreground" strokeWidth={1.8} />
            <span className="font-medium text-foreground">
              {fieldValue(change.to, emptyValueLabel)}
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}
