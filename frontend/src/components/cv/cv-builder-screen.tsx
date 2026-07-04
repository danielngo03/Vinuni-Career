"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowSquareOut,
  DownloadSimple,
  Eye,
  FileArrowUp,
  PencilSimple,
  Plus,
  SignIn,
  Star,
  WarningCircle,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import {
  Button,
  EmptyState,
  Select,
  Skeleton,
  StatusBadge,
  Tabs,
  TabPanel,
  useToast,
  type StatusTone,
} from "@/components/ui";
import { CvExportModal } from "./cv-export-modal";
import { CvVersionCard } from "./cv-version-card";
import { CvAiAssistCard } from "./cv-ai-assist-card";
import { CvJobFitRail } from "./cv-job-fit-rail";
import { SaveIndicator, type SaveState } from "./builder/save-indicator";
import { DocumentHealthCard } from "./builder/document-health-card";
import { OutlineRail } from "./builder/outline-rail";
import { DraggableSectionItem } from "./builder/draggable-section-item";
import { CvCanvasEditor } from "./builder/cv-canvas-editor";
import { CanvasInspector } from "./builder/canvas-inspector";
import { CvPhotoEditor, type PhotoShape } from "./builder/cv-photo-editor";
import { CvAiCommandBar } from "./builder/cv-ai-command-bar";
import {
  ApiError,
  cvApi,
  readImportOrigin,
  resolveDownloadUrl,
  type CvCanvasBlock,
  type CvCanvasBlockStyle,
  type CvSection,
  type CvSectionContent,
  type ImportOrigin,
} from "@/lib/api";
import { sectionTypeKey } from "@/lib/cv/sections";
import {
  blocksEqual,
  moveBlock,
  reconcileBlocks,
  setBlockStyle,
  shiftBlock,
  toggleBlockVisible,
} from "@/lib/cv/canvas";
import { useHistory } from "@/lib/cv/use-history";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { cn } from "@/lib/utils";

const STATUS_TONE: Record<string, StatusTone> = {
  draft: "draft",
  ready: "active",
  archived: "closed",
};
const AUTOSAVE_DELAY_MS = 1200;

export function CvBuilderScreen({ cvId, initialSuggestionId, jobId }: { cvId: string; initialSuggestionId?: string; jobId?: string }) {
  const t = useTranslations("cv");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const toast = useToast();
  const apiError = useApiErrorMessage();

  const query = useQuery({
    queryKey: ["cv", "detail", cvId],
    queryFn: () => cvApi.get(cvId),
    retry: false,
  });

  // ---- Local working copy (single source for editor + live A4 preview) ----
  const [sections, setSections] = useState<CvSection[]>([]);
  const [title, setTitle] = useState("");
  const [isPrimary, setIsPrimary] = useState(false);
  const [templateId, setTemplateId] = useState<string>("");
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [liveVersion, setLiveVersion] = useState(0);
  const [conflict, setConflict] = useState(false);
  const [mobileTab, setMobileTab] = useState("edit");
  const [exportOpen, setExportOpen] = useState(false);
  const [restoringId, setRestoringId] = useState<string | null>(null);
  const [addingSection, setAddingSection] = useState(false);
  // Drag-to-reorder (pointer); the up/down buttons remain the keyboard path.
  const [armedId, setArmedId] = useState<string | null>(null);
  const [dragId, setDragId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);
  // Best-effort original-document link for imported CVs (session-scoped).
  const [origin, setOrigin] = useState<ImportOrigin | null>(null);

  // ---- Canvas (block layout) editor state ----
  const blocksHistory = useHistory<CvCanvasBlock[]>([]);
  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);
  const [photoOpen, setPhotoOpen] = useState(false);
  const [photoSaving, setPhotoSaving] = useState(false);
  // The blocks value we last persisted/hydrated — any later `blocksHistory.value`
  // change (push, undo, or redo) that differs from this is a real canvas edit.
  const blocksPersistedRef = useRef<CvCanvasBlock[] | null>(null);

  const sectionsRef = useRef<CvSection[]>([]);
  const titleRef = useRef("");
  const versionRef = useRef(0);
  const hydratedRef = useRef<string | null>(null);
  const forceHydrateRef = useRef(false);
  const queueRef = useRef<Promise<unknown>>(Promise.resolve());
  const timersRef = useRef<Record<string, number>>({});

  const templates = useQuery({
    queryKey: ["cv", "templates"],
    queryFn: () => cvApi.listTemplates(),
    staleTime: 5 * 60_000,
  });

  // Keep refs in sync with state for use inside the async save queue.
  useEffect(() => {
    sectionsRef.current = sections;
  }, [sections]);
  useEffect(() => {
    titleRef.current = title;
  }, [title]);

  // Hydrate local state from the server on first load and after conflict reload.
  const data = query.data;
  useEffect(() => {
    if (!data) return;
    if (hydratedRef.current === data.id && !forceHydrateRef.current) return;
    setSections(data.sections);
    setTitle(data.title);
    setIsPrimary(data.is_primary);
    setTemplateId(data.template_id ?? "");
    versionRef.current = data.version;
    setLiveVersion(data.version);
    const reconciled = reconcileBlocks(data.canvas?.blocks, data.sections);
    blocksHistory.clear(reconciled);
    blocksPersistedRef.current = reconciled;
    setSelectedBlockId((prev) =>
      prev && reconciled.some((b) => b.id === prev) ? prev : null,
    );
    hydratedRef.current = data.id;
    forceHydrateRef.current = false;
    setSaveState("idle");
    // blocksHistory identity is stable across renders (see useHistory); omit it
    // from deps to avoid re-hydrating on every local canvas edit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  // Keep the canvas block layout reconciled when sections are added/removed
  // by the (non-canvas) section editor, without discarding local block order.
  useEffect(() => {
    if (hydratedRef.current !== data?.id) return;
    const reconciled = reconcileBlocks(blocksHistory.value, sections);
    if (!blocksEqual(reconciled, blocksHistory.value)) {
      blocksHistory.replace(reconciled);
      blocksPersistedRef.current = reconciled;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sections]);

  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      Object.values(timers).forEach((id) => window.clearTimeout(id));
    };
  }, []);

  useEffect(() => {
    setOrigin(readImportOrigin(cvId));
  }, [cvId]);

  const enqueue = useCallback((task: () => Promise<void>) => {
    queueRef.current = queueRef.current.then(task, task);
    return queueRef.current;
  }, []);

  const handleConflict = useCallback(async () => {
    setConflict(true);
    setSaveState("idle");
    forceHydrateRef.current = true;
    await query.refetch();
  }, [query]);

  // Persist a single section using the current optimistic version token.
  const persistSection = useCallback(
    (sectionId: string) =>
      enqueue(async () => {
        const sec = sectionsRef.current.find((s) => s.id === sectionId);
        if (!sec) return;
        setSaveState("saving");
        try {
          const res = await cvApi.upsertSection(cvId, sectionId, {
            title: sec.title,
            sort_order: sec.sort_order,
            is_visible: sec.is_visible,
            content: sec.content,
            expected_version: versionRef.current,
          });
          versionRef.current = res.cv_version;
          setLiveVersion(res.cv_version);
          setSaveState("saved");
        } catch (e) {
          if (e instanceof ApiError && e.code === "CONFLICT") {
            await handleConflict();
          } else {
            setSaveState("error");
            toast.show({ tone: "error", title: apiError(e) });
          }
        }
      }),
    [cvId, enqueue, handleConflict, toast, apiError],
  );

  const persistMeta = useCallback(
    (patch: { title?: string; is_primary?: boolean; template_id?: string | null }) =>
      enqueue(async () => {
        setSaveState("saving");
        try {
          const res = await cvApi.update(cvId, {
            ...patch,
            expected_version: versionRef.current,
          });
          versionRef.current = res.version;
          setLiveVersion(res.version);
          setSaveState("saved");
        } catch (e) {
          if (e instanceof ApiError && e.code === "CONFLICT") {
            await handleConflict();
          } else {
            setSaveState("error");
            toast.show({ tone: "error", title: apiError(e) });
          }
        }
      }),
    [cvId, enqueue, handleConflict, toast, apiError],
  );

  // Persist the canvas block layout (order/visibility/style). Discrete block
  // operations commit immediately — no debounce, unlike free-text keystrokes.
  const persistCanvasBlocks = useCallback(
    (blocks: CvCanvasBlock[]) =>
      enqueue(async () => {
        setSaveState("saving");
        try {
          const res = await cvApi.updateCanvas(cvId, {
            blocks,
            expected_version: versionRef.current,
          });
          versionRef.current = res.version;
          setLiveVersion(res.version);
          setSaveState("saved");
        } catch (e) {
          if (e instanceof ApiError && e.code === "CONFLICT") {
            await handleConflict();
          } else {
            setSaveState("error");
            toast.show({ tone: "error", title: apiError(e) });
          }
        }
      }),
    [cvId, enqueue, handleConflict, toast, apiError],
  );

  // Any real change to `blocksHistory.value` — from a push, an undo, or a
  // redo — is autosaved uniformly here (undo/redo are themselves autosaved).
  useEffect(() => {
    const current = blocksHistory.value;
    const last = blocksPersistedRef.current;
    if (last !== null && !blocksEqual(last, current)) {
      void persistCanvasBlocks(current);
    }
    blocksPersistedRef.current = current;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blocksHistory.value]);

  // Cmd/Ctrl+Z / Shift+Z undo/redo for canvas operations. Skips when focus is
  // in an editable text field so the browser's native text undo still works.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "z") return;
      const active = document.activeElement as HTMLElement | null;
      const isEditable =
        active?.isContentEditable ||
        active?.tagName === "INPUT" ||
        active?.tagName === "TEXTAREA";
      if (isEditable) return;
      e.preventDefault();
      if (e.shiftKey) blocksHistory.redo();
      else blocksHistory.undo();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleMoveBlock(fromId: string, toId: string) {
    blocksHistory.push(moveBlock(blocksHistory.value, fromId, toId));
  }
  function handleShiftBlock(blockId: string, direction: "up" | "down") {
    blocksHistory.push(shiftBlock(blocksHistory.value, blockId, direction));
  }
  function handleToggleBlockVisible(blockId: string, visible: boolean) {
    blocksHistory.push(toggleBlockVisible(blocksHistory.value, blockId, visible));
  }
  function handleBlockStyleChange(style: CvCanvasBlockStyle) {
    if (!selectedBlockId) return;
    blocksHistory.push(setBlockStyle(blocksHistory.value, selectedBlockId, style));
  }

  // ---- Photo replace/crop/remove (versioned; refetches for the canonical URL) ----
  const persistPhoto = useCallback(
    (form: {
      file?: File;
      cropX?: number;
      cropY?: number;
      cropWidth?: number;
      cropHeight?: number;
      shape?: PhotoShape;
    }) =>
      enqueue(async () => {
        setPhotoSaving(true);
        try {
          const res = await cvApi.updatePhoto(cvId, {
            ...form,
            expectedVersion: versionRef.current,
          });
          versionRef.current = res.version;
          setLiveVersion(res.version);
          forceHydrateRef.current = true;
          await query.refetch();
          setPhotoOpen(false);
          toast.show({ tone: "success", title: t("canvas.photoSavedToast") });
        } catch (e) {
          if (e instanceof ApiError && e.code === "CONFLICT") {
            await handleConflict();
          } else {
            toast.show({ tone: "error", title: apiError(e) });
          }
        } finally {
          setPhotoSaving(false);
        }
      }),
    [cvId, enqueue, handleConflict, toast, apiError, query, t],
  );

  const scheduleAutosave = useCallback(
    (sectionId: string) => {
      if (timersRef.current[sectionId]) {
        window.clearTimeout(timersRef.current[sectionId]);
      }
      timersRef.current[sectionId] = window.setTimeout(() => {
        delete timersRef.current[sectionId];
        void persistSection(sectionId);
      }, AUTOSAVE_DELAY_MS);
    },
    [persistSection],
  );

  const flushSection = useCallback(
    (sectionId: string) => {
      if (timersRef.current[sectionId]) {
        window.clearTimeout(timersRef.current[sectionId]);
        delete timersRef.current[sectionId];
      }
      void persistSection(sectionId);
    },
    [persistSection],
  );

  // ---- Editor mutations on the local working copy ----
  function changeSectionContent(sectionId: string, content: CvSectionContent) {
    setSections((prev) =>
      prev.map((s) => (s.id === sectionId ? { ...s, content } : s)),
    );
    scheduleAutosave(sectionId);
  }

  function toggleVisible(sectionId: string, visible: boolean) {
    setSections((prev) =>
      prev.map((s) => (s.id === sectionId ? { ...s, is_visible: visible } : s)),
    );
    flushSection(sectionId);
  }

  function moveSection(sectionId: string, direction: "up" | "down") {
    const idx = sections.findIndex((s) => s.id === sectionId);
    const j = direction === "up" ? idx - 1 : idx + 1;
    if (idx < 0 || j < 0 || j >= sections.length) return;
    const a = sections[idx]!;
    const b = sections[j]!;
    // Swap both array order and sort_order values.
    const next = [...sections];
    next[idx] = { ...b, sort_order: a.sort_order };
    next[j] = { ...a, sort_order: b.sort_order };
    setSections(next);
    // Persist both (serialized; version advances between writes).
    void persistSection(a.id);
    void persistSection(b.id);
  }

  // Drag-to-reorder: move `dragId` to the position of `targetId`, renumber
  // sort_order densely (0..n-1), and persist only the rows whose order changed.
  function dropOnto(targetId: string) {
    if (!dragId || dragId === targetId) return;
    const prev = sections;
    const fromIdx = prev.findIndex((s) => s.id === dragId);
    const toIdx = prev.findIndex((s) => s.id === targetId);
    if (fromIdx < 0 || toIdx < 0) return;
    const reordered = [...prev];
    const [moved] = reordered.splice(fromIdx, 1);
    reordered.splice(toIdx, 0, moved!);
    const renumbered = reordered.map((s, i) => ({ ...s, sort_order: i }));
    setSections(renumbered);
    const prevOrder = new Map(prev.map((s) => [s.id, s.sort_order]));
    for (const s of renumbered) {
      if (prevOrder.get(s.id) !== s.sort_order) void persistSection(s.id);
    }
  }

  function handleTitleChange(value: string) {
    setTitle(value);
  }
  function flushTitle() {
    if (titleRef.current.trim() && titleRef.current !== data?.title) {
      void persistMeta({ title: titleRef.current.trim() });
    }
  }

  function handleSetPrimary() {
    setIsPrimary(true);
    void persistMeta({ is_primary: true });
  }

  function handleTemplateChange(value: string) {
    setTemplateId(value);
    void persistMeta({ template_id: value || null });
  }

  async function handleAddSection() {
    setAddingSection(true);
    try {
      const res = await cvApi.addSection(cvId, {
        section_type: "custom",
        title: t("builder.newSectionTitle"),
        is_visible: true,
        content: { items: [] },
        expected_version: versionRef.current,
      });
      versionRef.current = res.cv_version;
      forceHydrateRef.current = true;
      await query.refetch();
      toast.show({ tone: "success", title: t("builder.sectionAdded") });
    } catch (e) {
      if (e instanceof ApiError && e.code === "CONFLICT") {
        await handleConflict();
      } else {
        toast.show({ tone: "error", title: apiError(e) });
      }
    } finally {
      setAddingSection(false);
    }
  }

  async function handleRestore(versionId: string) {
    setRestoringId(versionId);
    try {
      const restored = await cvApi.restoreVersion(
        cvId,
        versionId,
        versionRef.current,
      );
      versionRef.current = restored.version;
      forceHydrateRef.current = true;
      await query.refetch();
      toast.show({ tone: "success", title: t("versions.restoredToast") });
    } catch (e) {
      if (e instanceof ApiError && e.code === "CONFLICT") {
        await handleConflict();
      } else {
        toast.show({ tone: "error", title: apiError(e) });
      }
    } finally {
      setRestoringId(null);
    }
  }

  // ---------------------------- Render states ----------------------------
  if (query.isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-40" />
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(340px,420px)]">
          <div className="space-y-4">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-36 w-full rounded-2xl" />
            ))}
          </div>
          <Skeleton className="hidden h-[560px] w-full rounded-2xl lg:block" />
        </div>
      </div>
    );
  }

  if (query.isError) {
    const err = query.error;
    const isAuth = err instanceof ApiError && err.isAuthError;
    const isNotFound = err instanceof ApiError && err.isNotFound;
    return (
      <EmptyState
        kind={isAuth ? "auth" : "error"}
        icon={isAuth ? SignIn : WarningCircle}
        title={
          isAuth
            ? tStates("authTitle")
            : isNotFound
              ? t("builder.notFoundTitle")
              : tStates("errorTitle")
        }
        description={
          isAuth
            ? tStates("authBody")
            : isNotFound
              ? t("builder.notFoundBody")
              : tStates("errorBody")
        }
        action={
          <Link href="/student/cv">
            <Button variant="secondary">{t("builder.backToList")}</Button>
          </Link>
        }
      />
    );
  }

  const detail = data!;
  const versionId =
    detail.current_version_id ?? detail.versions?.[0]?.id ?? null;

  const sectionLabel = (s: CvSection) => {
    const key = `sectionTypes.${sectionTypeKey(s.section_type)}`;
    return t.has(key) ? t(key) : s.title;
  };
  const visibleCount = sections.filter((s) => s.is_visible).length;
  const activeTemplateName =
    templates.data?.find((tpl) => tpl.id === templateId)?.name ?? null;

  function scrollToSection(id: string) {
    if (typeof document === "undefined") return;
    document
      .getElementById(`cv-sec-${id}`)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  const saveIndicator = <SaveIndicator state={saveState} />;

  // ---- Canvas selection + inspector wiring ----
  const orderedBlocks = [...blocksHistory.value].sort((a, b) => a.order - b.order);
  const selectedBlock = orderedBlocks.find((b) => b.id === selectedBlockId) ?? null;
  const selectedBlockIndex = selectedBlock
    ? orderedBlocks.findIndex((b) => b.id === selectedBlock.id)
    : -1;
  const selectedSection =
    selectedBlock?.section_id != null
      ? (sections.find((s) => s.id === selectedBlock.section_id) ?? null)
      : null;
  const canvasPhoto = detail.canvas?.photo ?? null;

  const editorPanel = (
    <div className="space-y-4">
      {/* Meta controls */}
      <div className="rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] backdrop-blur-md p-4 shadow-[var(--shadow-sm)] sm:p-5">
        <label
          htmlFor="cv-title"
          className="mb-1.5 block text-sm font-semibold text-[var(--text-primary)]"
        >
          {t("builder.titleLabel")}
        </label>
        <input
          id="cv-title"
          value={title}
          onChange={(e) => handleTitleChange(e.target.value)}
          onBlur={flushTitle}
          className="w-full rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] px-3.5 py-2.5 text-sm font-medium text-[var(--text-primary)] outline-none transition-colors backdrop-blur-sm focus:border-[var(--brand-primary)]/50 focus:bg-[var(--glass-surface-heavy)] focus:ring-2 focus:ring-[var(--brand-primary)]/30"
        />
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <Select
            label={t("builder.templateLabel")}
            value={templateId}
            onChange={(e) => handleTemplateChange(e.target.value)}
            disabled={templates.isPending}
            options={[
              { value: "", label: t("create.templateNone") },
              ...(templates.data ?? []).map((tpl) => ({
                value: tpl.id,
                label: tpl.name,
              })),
            ]}
          />
          <div className="flex items-end">
            <Button
              variant={isPrimary ? "ghost" : "secondary"}
              disabled={isPrimary}
              onClick={handleSetPrimary}
              fullWidth
            >
              <Star
                aria-hidden
                weight={isPrimary ? "fill" : "bold"}
                className="size-4"
              />
              {isPrimary ? t("builder.isPrimary") : t("builder.setPrimary")}
            </Button>
          </div>
        </div>
      </div>

      {/* AI Document Health — derived from live section state */}
      <DocumentHealthCard sections={sections} />

      {/* Sections */}
      {sections.map((s, i) => (
        <DraggableSectionItem
          key={s.id}
          section={s}
          index={i}
          total={sections.length}
          dragActive={dragId !== null}
          isDragging={dragId === s.id}
          isDropTarget={overId === s.id}
          isArmed={armedId === s.id}
          onArmDrag={() => setArmedId(s.id)}
          onDragStart={() => setDragId(s.id)}
          onDragOverSection={() => setOverId(s.id)}
          onDropOnSection={() => {
            dropOnto(s.id);
            setDragId(null);
            setOverId(null);
            setArmedId(null);
          }}
          onDragEnd={() => {
            setDragId(null);
            setOverId(null);
            setArmedId(null);
          }}
          onContentChange={(content) => changeSectionContent(s.id, content)}
          onFlush={() => flushSection(s.id)}
          onToggleVisible={(v) => toggleVisible(s.id, v)}
          onMove={(dir) => moveSection(s.id, dir)}
        />
      ))}

      <Button
        variant="secondary"
        fullWidth
        loading={addingSection}
        onClick={handleAddSection}
      >
        <Plus aria-hidden weight="bold" className="size-4" />
        {t("builder.addSection")}
      </Button>
    </div>
  );

  const previewPanel = (
    <div className="space-y-4 lg:sticky lg:top-4">
      <CvCanvasEditor
        title={title}
        sections={sections}
        blocks={blocksHistory.value}
        selectedBlockId={selectedBlockId}
        onSelectBlock={setSelectedBlockId}
        onMoveBlock={handleMoveBlock}
        onShiftBlock={handleShiftBlock}
        onToggleBlockVisible={handleToggleBlockVisible}
        onSectionTextChange={changeSectionContent}
        onSectionTextFlush={flushSection}
        photo={canvasPhoto}
        onEditPhoto={() => setPhotoOpen(true)}
      />
      <div className="flex items-center justify-end gap-2 text-xs text-[var(--text-muted)]">
        <button
          type="button"
          onClick={() => blocksHistory.undo()}
          disabled={!blocksHistory.canUndo}
          className="rounded-lg border border-[var(--glass-border-strong)] px-2.5 py-1 font-semibold outline-none hover:bg-[var(--glass-surface-light)] disabled:opacity-30"
        >
          {t("canvas.undo")}
        </button>
        <button
          type="button"
          onClick={() => blocksHistory.redo()}
          disabled={!blocksHistory.canRedo}
          className="rounded-lg border border-[var(--glass-border-strong)] px-2.5 py-1 font-semibold outline-none hover:bg-[var(--glass-surface-light)] disabled:opacity-30"
        >
          {t("canvas.redo")}
        </button>
      </div>
      <CanvasInspector
        block={selectedBlock}
        section={selectedSection}
        index={selectedBlockIndex}
        total={orderedBlocks.length}
        onStyleChange={handleBlockStyleChange}
        onToggleVisible={(visible) => selectedBlockId && handleToggleBlockVisible(selectedBlockId, visible)}
        onShift={(direction) => selectedBlockId && handleShiftBlock(selectedBlockId, direction)}
      />
      <CvAiCommandBar
        cvId={cvId}
        onApplied={() => {
          forceHydrateRef.current = true;
          void query.refetch();
        }}
      />
      {origin && origin.previewUrl && (
        <div className="rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] backdrop-blur-md p-3.5 shadow-[var(--shadow-sm)]">
          <p className="mb-1.5 text-xs font-bold uppercase tracking-wide text-[var(--text-muted)]">
            {t("builder.originalTitle")}
          </p>
          <div className="flex items-center gap-2.5">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg icon-chip-primary shadow-sm">
              <FileArrowUp
                aria-hidden
                weight="duotone"
                className="size-5 text-white"
              />
            </span>
            <div className="min-w-0 flex-1">
              <p
                className="truncate text-sm font-medium text-[var(--text-primary)]"
                title={origin.filename}
              >
                {origin.filename}
              </p>
              <a
                href={resolveDownloadUrl(origin.previewUrl)}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--brand-primary)] outline-none hover:underline focus-visible:underline"
              >
                <ArrowSquareOut aria-hidden weight="bold" className="size-3.5" />
                {t("builder.viewOriginal")}
              </a>
            </div>
          </div>
        </div>
      )}
      <CvVersionCard
        version={liveVersion}
        lastEditedAt={detail.last_edited_at}
        versions={detail.versions}
        onRestore={handleRestore}
        restoringId={restoringId}
      />
      <CvAiAssistCard cvId={cvId} sections={sections} initialSuggestionId={initialSuggestionId} />
      <CvJobFitRail cvId={cvId} jobId={jobId} />
    </div>
  );

  // Left document-outline rail (desktop xl+). Navigation-only mirror of the
  // section list so the builder reads like a document editor, not a stacked
  // form. Form controls (template/primary) stay single-instance in the editor.
  const outlineRail = (
    <OutlineRail
      sections={sections}
      visibleCount={visibleCount}
      activeTemplateName={activeTemplateName}
      addingSection={addingSection}
      sectionLabel={sectionLabel}
      onScrollTo={scrollToSection}
      onAddSection={handleAddSection}
    />
  );

  return (
    <div>
      {/* Editor app bar */}
      <div className="mb-4 flex flex-col gap-3 border-b border-[var(--glass-border)] pb-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-2.5">
          <Link
            href="/student/cv"
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2 py-1 text-sm font-medium text-[var(--text-secondary)] outline-none hover:text-[var(--brand-primary)] focus-visible:underline"
          >
            <ArrowLeft aria-hidden weight="bold" className="size-4" />
            <span className="hidden sm:inline">{t("builder.backToList")}</span>
          </Link>
          <span className="hidden text-[var(--border-strong)] sm:inline">/</span>
          <h1 className="min-w-0 truncate text-lg font-bold tracking-tight text-[var(--text-primary)]">
            {title || t("preview.untitled")}
          </h1>
          <StatusBadge tone={STATUS_TONE[detail.status] ?? "info"}>
            {detail.status_label}
          </StatusBadge>
        </div>
        <div className="flex items-center gap-3">
          {saveIndicator}
          <Button variant="primary" onClick={() => setExportOpen(true)}>
            <DownloadSimple aria-hidden weight="bold" className="size-4" />
            {t("builder.export")}
          </Button>
        </div>
      </div>

      {conflict && (
        <div
          role="alert"
          className="mb-4 flex items-start gap-3 rounded-xl border border-[var(--amber-600)]/40 bg-[var(--amber-100)] p-3.5"
        >
          <span className="flex size-7 shrink-0 items-center justify-center rounded-lg icon-chip-warning shadow-sm">
            <WarningCircle aria-hidden weight="duotone" className="size-4 text-white" />
          </span>
          <div className="flex-1">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {t("builder.conflictTitle")}
            </p>
            <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
              {t("builder.conflictBody")}
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={() => setConflict(false)}>
            {tc("close")}
          </Button>
        </div>
      )}

      {/* Mobile tabs */}
      <div className="lg:hidden">
        <Tabs
          ariaLabel={t("builder.tabsLabel")}
          value={mobileTab}
          onValueChange={setMobileTab}
          idBase="cv-builder"
          items={[
            {
              value: "edit",
              label: t("builder.tabEdit"),
              icon: <PencilSimple aria-hidden weight="duotone" className="size-4" />,
            },
            {
              value: "preview",
              label: t("builder.tabPreview"),
              icon: <Eye aria-hidden weight="duotone" className="size-4" />,
            },
          ]}
        />
      </div>

      {/* Single instance of each panel; CSS arranges the document-builder
          panes side-by-side (outline rail / editor / preview) on desktop and
          tab-toggles editor/preview on mobile (no duplicated DOM / ids). */}
      <div className="mt-4 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(340px,400px)] lg:gap-5 xl:grid-cols-[210px_minmax(0,1fr)_minmax(360px,400px)]">
        {outlineRail}
        <TabPanel tabsId="cv-builder" value="edit" active>
          <div
            className={cn(
              "lg:block",
              mobileTab === "edit" ? "block" : "hidden",
            )}
          >
            {editorPanel}
          </div>
        </TabPanel>
        <TabPanel tabsId="cv-builder" value="preview" active>
          <div
            className={cn(
              "lg:block",
              mobileTab === "preview" ? "block" : "hidden",
            )}
          >
            {previewPanel}
          </div>
        </TabPanel>
      </div>

      <CvExportModal
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        cvId={cvId}
        versionId={versionId}
      />

      <CvPhotoEditor
        open={photoOpen}
        onClose={() => setPhotoOpen(false)}
        currentPhoto={canvasPhoto}
        saving={photoSaving}
        onSave={({ file, crop, shape }) =>
          void persistPhoto({
            file,
            cropX: crop.x,
            cropY: crop.y,
            cropWidth: crop.width,
            cropHeight: crop.height,
            shape,
          })
        }
        onRemove={() => void persistPhoto({})}
      />
    </div>
  );
}
