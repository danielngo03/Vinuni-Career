"use client";

import {
  CheckCircle,
  FileArrowUp,
  FileText,
  PencilSimple,
  Robot,
  SpinnerGap,
  Star,
  Trash,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { apiFetch, apiMessage } from "@/lib/api/client";
import type { AIRun, CV } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/provider";

type InspectResult = {
  route: string;
  detected_kind: string;
  byte_size: number;
  reasons: string[];
  needs_vision: boolean;
  extracted_text_preview: string;
};

type AnalysisState = {
  cvId: string;
  runId: string;
  status: string;
};

export function CVCenter() {
  const { locale, dictionary } = useI18n();
  const [cvs, setCvs] = useState<CV[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [workingId, setWorkingId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [selectedCvId, setSelectedCvId] = useState<string | null>(null);
  const [rawDraft, setRawDraft] = useState("");
  const [rawEditing, setRawEditing] = useState(false);
  const [analysis, setAnalysis] = useState<AnalysisState | null>(null);
  const [creatingBlank, setCreatingBlank] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const cvData = await apiFetch<CV[]>("/cvs/me");
      setCvs(cvData);
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

  const selectedCv = useMemo(
    () => cvs.find((cv) => cv.id === selectedCvId) || cvs[0] || null,
    [cvs, selectedCvId],
  );

  useEffect(() => {
    if (!cvs.length) {
      setSelectedCvId(null);
      setRawDraft("");
      return;
    }
    if (!selectedCvId || !cvs.some((cv) => cv.id === selectedCvId)) {
      setSelectedCvId(cvs[0].id);
    }
  }, [cvs, selectedCvId]);

  useEffect(() => {
    if (!selectedCv || rawEditing) return;
    setRawDraft(rawTextForCv(selectedCv, dictionary.common.empty));
  }, [selectedCv, rawEditing, dictionary.common.empty]);

  useEffect(() => {
    if (!analysis || !["QUEUED", "RUNNING"].includes(analysis.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const run = await apiFetch<AIRun>(`/ai/runs/${analysis.runId}`);
        setAnalysis((current) =>
          current?.runId === run.run_id
            ? { ...current, status: run.status }
            : current,
        );
        if (["DONE", "FAILED", "CANCELLED"].includes(run.status)) {
          if (run.status === "DONE") {
            toast.success(dictionary.ai.completed);
          } else if (run.status === "FAILED") {
            toast.error(run.error || dictionary.ai.failed);
          }
          window.setTimeout(() => {
            setAnalysis((current) => (current?.runId === run.run_id ? null : current));
          }, 3500);
        }
      } catch (error) {
        toast.error(apiMessage(error, dictionary.ai.failed));
        setAnalysis(null);
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [analysis, dictionary.ai.completed, dictionary.ai.failed]);

  function selectCv(cv: CV) {
    setSelectedCvId(cv.id);
    setRawDraft(rawTextForCv(cv, dictionary.common.empty));
    setRawEditing(false);
  }

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

  async function createBlankCv() {
    setCreatingBlank(true);
    try {
      const cv = await apiFetch<CV>("/cvs/blank", { method: "POST" });
      setCvs((current) => [cv, ...current.filter((item) => item.id !== cv.id)]);
      setSelectedCvId(cv.id);
      setRawDraft(rawTextForCv(cv, dictionary.common.empty));
      setRawEditing(true);
      toast.success(dictionary.common.updated);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setCreatingBlank(false);
    }
  }

  async function analyze(cv: CV, rawText = rawTextForCv(cv, dictionary.common.empty)) {
    if (!rawText.trim()) {
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
          run_metadata: {
            raw_text: rawText.trim(),
            source_quality: "native_text",
          },
        }),
      });
      setAnalysis({ cvId: cv.id, runId: run.run_id, status: run.status });
      toast.success(`${dictionary.ai.running} - ${run.run_id.slice(0, 8)}`);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.ai.failed));
    } finally {
      setWorkingId(null);
    }
  }

  const selectedAnalysisStatus =
    selectedCv && analysis?.cvId === selectedCv.id ? analysis.status : null;
  const selectedAnalysisRunning = selectedAnalysisStatus
    ? ["QUEUED", "RUNNING"].includes(selectedAnalysisStatus)
    : false;

  return (
    <>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
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
            <Button
              variant="outline"
              onClick={createBlankCv}
              disabled={creatingBlank || cvs.length >= 5}
            >
              {creatingBlank ? (
                <SpinnerGap className="size-4 animate-spin" />
              ) : (
                <FileText className="size-4" />
              )}
              Tạo CV rỗng
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
            {!loading && selectedCv ? (
              <div>
                <div className="flex flex-col gap-3 border-b pb-4 sm:flex-row sm:items-start">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold">{selectedCv.title}</h3>
                      {selectedCv.is_primary ? (
                        <Badge tone="green">
                          <Star className="mr-1 size-3" weight="fill" />
                          Primary
                        </Badge>
                      ) : null}
                      {selectedAnalysisStatus ? (
                        <Badge
                          tone={
                            selectedAnalysisStatus === "FAILED"
                              ? "red"
                              : selectedAnalysisStatus === "DONE"
                                ? "green"
                                : "amber"
                          }
                        >
                          {selectedAnalysisRunning ? (
                            <SpinnerGap className="mr-1 size-3 animate-spin" />
                          ) : null}
                          {selectedAnalysisStatus === "DONE"
                            ? dictionary.ai.completed
                            : selectedAnalysisStatus === "FAILED"
                              ? dictionary.ai.failed
                              : "Đang phân tích"}
                        </Badge>
                      ) : null}
                    </div>
                    <p className="mt-1 text-xs text-muted">
                      {new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(
                        new Date(selectedCv.created_at),
                      )}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant={rawEditing ? "outline" : "ghost"}
                      size="sm"
                      onClick={() => setRawEditing((current) => !current)}
                    >
                      <PencilSimple className="size-4" />
                      {rawEditing ? "Xem Markdown" : "Edit"}
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => analyze(selectedCv, rawDraft)}
                      disabled={workingId === selectedCv.id || selectedAnalysisRunning}
                    >
                      {workingId === selectedCv.id || selectedAnalysisRunning ? (
                        <SpinnerGap className="size-4 animate-spin" />
                      ) : (
                        <Robot className="size-4" weight="duotone" />
                      )}
                      {selectedAnalysisRunning ? "Đang phân tích" : "Phân tích lại"}
                    </Button>
                  </div>
                </div>

                <div className="relative">
                  {selectedAnalysisRunning ? (
                    <div className="pointer-events-none absolute right-4 top-8 z-10 inline-flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800 shadow-sm">
                      <SpinnerGap className="size-4 animate-spin" />
                      AI đang phân tích CV này
                    </div>
                  ) : null}
                  {rawEditing ? (
                    <textarea
                      value={rawDraft}
                      onChange={(event) => setRawDraft(event.target.value)}
                      className="focus-ring mt-4 min-h-[520px] w-full resize-y rounded-xl border bg-slate-50 p-4 font-mono text-sm leading-6"
                      spellCheck={false}
                    />
                  ) : (
                    <MarkdownPreview content={rawDraft} busy={selectedAnalysisRunning} />
                  )}
                </div>
              </div>
            ) : null}
          </div>
        </section>

        <section className="rounded-2xl border bg-white p-5">
          <div className="flex items-center justify-between gap-3">
            <h2 className="font-semibold">Chọn CV</h2>
            <Badge tone="blue">{cvs.length}/5</Badge>
          </div>
          <p className="mt-2 text-sm leading-6 text-muted">
            Chọn CV để xem raw content dạng Markdown, chỉnh sửa, rồi gửi phân tích lại.
          </p>
          <div className="mt-5 space-y-3">
            {loading ? <PanelSkeleton /> : null}
            {cvs.map((cv) => (
              <article
                key={cv.id}
                className={`rounded-xl border p-3 transition-colors ${
                  selectedCv?.id === cv.id ? "border-blue-300 bg-blue-50/50" : "bg-white"
                }`}
              >
                <button
                  type="button"
                  className="flex w-full items-start gap-3 text-left"
                  onClick={() => selectCv(cv)}
                >
                  <FileText className="mt-0.5 size-5 shrink-0 text-primary" weight="duotone" />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <p className="truncate text-sm font-semibold">{cv.title}</p>
                      {cv.is_primary ? (
                        <Badge tone="green" className="px-1.5 py-0.5">
                          Primary
                        </Badge>
                      ) : null}
                      {analysis?.cvId === cv.id &&
                      ["QUEUED", "RUNNING"].includes(analysis.status) ? (
                        <Badge tone="amber" className="px-1.5 py-0.5">
                          <SpinnerGap className="mr-1 size-3 animate-spin" />
                          Đang chạy
                        </Badge>
                      ) : null}
                    </div>
                    <p className="mt-1 text-xs text-muted">
                      {new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(
                        new Date(cv.created_at),
                      )}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {(cv.skills || []).length ? (
                        (cv.skills || []).slice(0, 8).map((skill) => (
                          <Badge key={skill} tone="blue" className="px-1.5 py-0.5">
                            {skill}
                          </Badge>
                        ))
                      ) : (
                        <span className="text-xs text-muted">{dictionary.common.empty}</span>
                      )}
                    </div>
                  </div>
                </button>
                <div className="mt-3 flex flex-wrap gap-2 border-t pt-3">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setEditingId(cv.id);
                      setEditTitle(cv.title);
                    }}
                    disabled={workingId === cv.id}
                    className="px-2"
                  >
                    <PencilSimple className="size-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => deleteCv(cv.id)}
                    disabled={workingId === cv.id}
                    className="px-2 text-red-500 hover:text-red-600"
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
                </div>
                {editingId === cv.id ? (
                  <div className="mt-3 flex items-center gap-2">
                    <Input
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      className="h-8 text-sm"
                      autoFocus
                      onKeyDown={(e) => {
                        if (e.key === "Enter") renameCv(cv.id);
                        if (e.key === "Escape") setEditingId(null);
                      }}
                    />
                    <Button size="sm" className="h-8 px-2" onClick={() => renameCv(cv.id)}>
                      <CheckCircle className="size-4" />
                    </Button>
                  </div>
                ) : null}
              </article>
            ))}
            {!cvs.length && !loading ? (
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

function rawTextForCv(cv: CV, emptyText: string) {
  if (typeof cv.parsed_data.raw_markdown === "string" && cv.parsed_data.raw_markdown.trim()) {
    return cv.parsed_data.raw_markdown;
  }
  const geminiExtraction = cv.parsed_data.gemini_extraction;
  if (
    geminiExtraction &&
    typeof geminiExtraction === "object" &&
    "raw_markdown" in geminiExtraction &&
    typeof geminiExtraction.raw_markdown === "string" &&
    geminiExtraction.raw_markdown.trim()
  ) {
    return geminiExtraction.raw_markdown;
  }
  if (typeof cv.parsed_data.raw_text === "string" && cv.parsed_data.raw_text.trim()) {
    return cv.parsed_data.raw_text;
  }
  const lines = [
    cv.title ? `# ${cv.title}` : "",
    cv.summary || (typeof cv.parsed_data.summary === "string" ? cv.parsed_data.summary : ""),
    cv.skills?.length ? `## Skills\n${cv.skills.map((skill) => `- ${skill}`).join("\n")}` : "",
  ].filter(Boolean);
  return lines.join("\n\n") || emptyText;
}

function MarkdownPreview({ content, busy = false }: { content: string; busy?: boolean }) {
  const lines = content.split(/\r?\n/);
  return (
    <div
      className={`mt-4 min-h-[520px] rounded-xl border bg-slate-50 p-5 transition-opacity ${
        busy ? "opacity-70" : "opacity-100"
      }`}
    >
      <div className="space-y-2 text-sm leading-7 text-slate-700">
        {lines.map((line, index) => {
          const key = `${index}-${line}`;
          if (!line.trim()) return <div key={key} className="h-2" />;
          if (line.startsWith("# ")) {
            return (
              <h1 key={key} className="text-2xl font-semibold leading-tight text-slate-950">
                {line.slice(2)}
              </h1>
            );
          }
          if (line.startsWith("## ")) {
            return (
              <h2 key={key} className="pt-3 text-lg font-semibold leading-tight text-slate-950">
                {line.slice(3)}
              </h2>
            );
          }
          if (line.startsWith("### ")) {
            return (
              <h3 key={key} className="pt-2 font-semibold leading-tight text-slate-900">
                {line.slice(4)}
              </h3>
            );
          }
          if (line.startsWith("- ")) {
            return (
              <p key={key} className="pl-4">
                <span className="mr-2 text-primary">•</span>
                {line.slice(2)}
              </p>
            );
          }
          return <p key={key}>{line}</p>;
        })}
      </div>
    </div>
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
        <span className="mt-1 text-xs text-muted">PDF, DOCX, TXT - 20MB max</span>
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
              <li key={reason}>- {reason}</li>
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
