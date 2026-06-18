"use client";

import {
  CheckCircle,
  FileArrowUp,
  FileText,
  PencilSimple,
  Robot,
  ShieldCheck,
  SpinnerGap,
  Star,
  Trash,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { apiFetch, apiMessage } from "@/lib/api/client";
import type { AIRun, CV, DocumentRecord } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { PanelSkeleton } from "@/components/ui/skeleton";

type InspectResult = {
  route: string;
  detected_kind: string;
  byte_size: number;
  reasons: string[];
  needs_vision: boolean;
  extracted_text_preview: string;
};

export function CVCenter() {
  const { locale, dictionary } = useI18n();
  const [cvs, setCvs] = useState<CV[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [workingId, setWorkingId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [cvData, documentData] = await Promise.all([
        apiFetch<CV[]>("/cvs/me"),
        apiFetch<DocumentRecord[]>("/documents/"),
      ]);
      setCvs(cvData);
      setDocuments(documentData);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setLoading(false);
    }
  }, [dictionary.common.retry]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function makePrimary(cvId: string) {
    setWorkingId(cvId);
    try {
      await apiFetch(`/cvs/${cvId}/primary`, { method: "PUT" });
      await load();
      toast.success(dictionary.common.updated);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setWorkingId(null);
    }
  }

  async function renameCv(cvId: string) {
    if (!editTitle.trim()) return;
    setWorkingId(cvId);
    try {
      await apiFetch(`/cvs/${cvId}`, {
        method: "PATCH",
        body: JSON.stringify({ title: editTitle }),
      });
      await load();
      setEditingId(null);
      toast.success(dictionary.common.updated);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setWorkingId(null);
    }
  }

  async function deleteCv(cvId: string) {
    if (!confirm(dictionary.common.delete + "?")) return;
    setWorkingId(cvId);
    try {
      await apiFetch(`/cvs/${cvId}`, { method: "DELETE" });
      await load();
      toast.success(dictionary.common.deleted || "Deleted successfully");
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setWorkingId(null);
    }
  }

  async function analyze(cv: CV) {
    const rawText =
      typeof cv.parsed_data.raw_text === "string"
        ? cv.parsed_data.raw_text
        : [cv.summary, ...(cv.skills || [])].filter(Boolean).join("\n");
    if (!rawText) {
      toast.error(dictionary.ai.input);
      return;
    }
    setWorkingId(cv.id);
    try {
      const run = await apiFetch<AIRun>("/ai/runs/", {
        method: "POST",
        body: JSON.stringify({
          run_type: "cv_extraction",
          input_ref: `cv:${cv.id}`,
          run_metadata: { raw_text: rawText },
        }),
      });
      toast.success(`${dictionary.ai.running} · ${run.run_id.slice(0, 8)}`);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.ai.failed));
    } finally {
      setWorkingId(null);
    }
  }

  return (
    <>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section className="rounded-2xl border bg-white">
          <div className="flex items-center gap-3 border-b p-5">
            <div>
              <h2 className="font-semibold">{dictionary.sections.cv}</h2>
              <p className="mt-1 text-sm text-muted">
                {dictionary.operations.student.cvDescription}
              </p>
            </div>
            <Button className="ml-auto" onClick={() => setUploadOpen(true)}>
              <FileArrowUp className="size-4" />
              {dictionary.documents.upload}
            </Button>
          </div>
          <div className="p-4 sm:p-5">
            {loading ? <PanelSkeleton /> : null}
            {!loading && !cvs.length ? (
              <EmptyState
                icon={FileText}
                title={dictionary.documents.noDocuments}
                description={dictionary.documents.noDocumentsDescription}
                action={dictionary.documents.upload}
                onAction={() => setUploadOpen(true)}
              />
            ) : null}
            {!loading && cvs.length ? (
              <div className="space-y-3">
                {cvs.map((cv) => (
                  <article key={cv.id} className="rounded-2xl border p-4">
                    <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
                      <div className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-blue-50 text-primary">
                        <FileText className="size-6" weight="duotone" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          {editingId === cv.id ? (
                            <div className="flex items-center gap-2">
                              <Input
                                value={editTitle}
                                onChange={(e) => setEditTitle(e.target.value)}
                                className="h-7 w-48 text-sm"
                                autoFocus
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") renameCv(cv.id);
                                  if (e.key === "Escape") setEditingId(null);
                                }}
                              />
                              <Button size="sm" className="h-7 px-2" onClick={() => renameCv(cv.id)}>
                                <CheckCircle className="size-4" />
                              </Button>
                            </div>
                          ) : (
                            <h3 className="font-semibold">{cv.title}</h3>
                          )}
                          {cv.is_primary ? (
                            <Badge tone="green">
                              <Star className="mr-1 size-3" weight="fill" />
                              Primary
                            </Badge>
                          ) : null}
                        </div>
                        <p className="mt-1 text-xs text-muted">
                          {new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(
                            new Date(cv.created_at),
                          )}
                        </p>
                        <p className="mt-3 line-clamp-2 text-sm leading-6 text-muted">
                          {cv.summary ||
                            (typeof cv.parsed_data.summary === "string"
                              ? cv.parsed_data.summary
                              : dictionary.common.empty)}
                        </p>
                        <div className="mt-3 flex flex-wrap gap-1.5">
                          {(cv.skills || []).slice(0, 10).map((skill) => (
                            <Badge key={skill} tone="blue">
                              {skill}
                            </Badge>
                          ))}
                        </div>
                      </div>
                      <div className="flex shrink-0 flex-wrap gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setEditingId(cv.id);
                            setEditTitle(cv.title);
                          }}
                          disabled={workingId === cv.id}
                        >
                          <PencilSimple className="size-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => deleteCv(cv.id)}
                          disabled={workingId === cv.id}
                          className="text-red-500 hover:text-red-600"
                        >
                          <Trash className="size-4" />
                        </Button>
                        {!cv.is_primary ? (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => makePrimary(cv.id)}
                            disabled={workingId === cv.id}
                          >
                            <CheckCircle className="size-4" />
                            Primary
                          </Button>
                        ) : null}
                        <Button
                          size="sm"
                          onClick={() => analyze(cv)}
                          disabled={workingId === cv.id}
                        >
                          {workingId === cv.id ? (
                            <SpinnerGap className="size-4 animate-spin" />
                          ) : (
                            <Robot className="size-4" weight="duotone" />
                          )}
                          {dictionary.ai.cvExtraction}
                        </Button>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            ) : null}
          </div>
        </section>

        <section className="rounded-2xl border bg-white p-5">
          <div className="flex items-center gap-2">
            <ShieldCheck className="size-5 text-primary" weight="duotone" />
            <h2 className="font-semibold">{dictionary.documents.title}</h2>
          </div>
          <p className="mt-2 text-sm leading-6 text-muted">
            {dictionary.documents.description}
          </p>
          <div className="mt-5 space-y-3">
            {documents.map((document) => (
              <div key={document.id} className="rounded-xl bg-slate-50 p-3">
                <div className="flex items-start gap-3">
                  <FileText className="mt-0.5 size-5 shrink-0 text-primary" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold">{document.file_name}</p>
                    <p className="mt-1 text-xs text-muted">
                      {(document.size_bytes / 1024).toFixed(1)} KB · {document.category}
                    </p>
                  </div>
                  <Badge
                    tone={
                      document.scan_status === "CLEAN"
                        ? "green"
                        : document.scan_status === "INFECTED"
                          ? "red"
                          : "amber"
                    }
                  >
                    {document.scan_status}
                  </Badge>
                </div>
              </div>
            ))}
            {!documents.length && !loading ? (
              <p className="rounded-xl bg-slate-50 p-4 text-sm text-muted">
                {dictionary.documents.noDocumentsDescription}
              </p>
            ) : null}
          </div>
        </section>
      </div>
      <CVUploadModal
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        onUploaded={load}
      />
    </>
  );
}

function CVUploadModal({
  open,
  onOpenChange,
  onUploaded,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUploaded: () => Promise<void>;
}) {
  const { dictionary } = useI18n();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [inspection, setInspection] = useState<InspectResult | null>(null);
  const [pending, setPending] = useState(false);

  async function inspect(selected: File) {
    const data = new FormData();
    data.set("upload", selected);
    try {
      const result = await apiFetch<InspectResult>("/cvs/inspect", {
        method: "POST",
        body: data,
      });
      setInspection(result);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    }
  }

  async function upload() {
    if (!file) return;
    setPending(true);
    const data = new FormData();
    data.set("file", file);
    if (title.trim()) data.set("title", title.trim());
    try {
      await apiFetch("/cvs/upload", { method: "POST", body: data });
      await onUploaded();
      onOpenChange(false);
      setFile(null);
      setInspection(null);
      toast.success(dictionary.common.updated);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setPending(false);
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={dictionary.documents.upload}
      description={dictionary.operations.student.cvDescription}
    >
      <label className="focus-ring flex cursor-pointer flex-col items-center rounded-2xl border border-dashed bg-slate-50 px-6 py-10 text-center hover:border-blue-300 hover:bg-blue-50/40">
        <FileArrowUp className="size-8 text-primary" weight="duotone" />
        <span className="mt-3 font-semibold">
          {file?.name || dictionary.documents.upload}
        </span>
        <span className="mt-1 text-xs text-muted">PDF, DOCX, TXT · 20MB max</span>
        <input
          type="file"
          accept=".pdf,.docx,.txt"
          className="sr-only"
          onChange={(event) => {
            const selected = event.target.files?.[0];
            if (!selected) return;
            setFile(selected);
            setTitle(selected.name);
            void inspect(selected);
          }}
        />
      </label>
      {file ? (
        <div className="mt-4">
          <label className="mb-1.5 block text-xs font-medium text-muted">
            {dictionary.common.name || "Custom Name"}
          </label>
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={file.name}
          />
        </div>
      ) : null}
      {inspection ? (
        <div className="mt-4 rounded-xl border bg-white p-4">
          <div className="flex items-center gap-2">
            <Badge tone={inspection.route === "reject" ? "red" : "green"}>
              {inspection.route}
            </Badge>
            <span className="text-xs text-muted">{inspection.detected_kind}</span>
          </div>
          <ul className="mt-3 space-y-1 text-xs leading-5 text-muted">
            {inspection.reasons.map((reason) => (
              <li key={reason}>• {reason}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <Button
        className="mt-5 w-full"
        onClick={upload}
        disabled={!file || pending || inspection?.route === "reject"}
      >
        {pending ? <SpinnerGap className="size-5 animate-spin" /> : <FileArrowUp className="size-4" />}
        {pending ? dictionary.forms.submitting : dictionary.documents.upload}
      </Button>
    </Modal>
  );
}
