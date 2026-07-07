"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowSquareOut,
  CheckCircle,
  DownloadSimple,
  FileArrowUp,
  FloppyDisk,
  ImageSquare,
  PaintBrushBroad,
  PuzzlePiece,
  Rows,
  SignIn,
  Sparkle,
  ClockCounterClockwise,
  WarningCircle,
} from "@phosphor-icons/react";
import { Link, useRouter } from "@/i18n/navigation";
import {
  Button,
  EmptyState,
  Skeleton,
  StatusBadge,
  Tabs,
  TabPanel,
  useToast,
} from "@/components/ui";
import { CvExportModal } from "./cv-export-modal";
import { CvQuotaModal } from "./cv-quota-modal";
import { VersionsPanel } from "./builder/versions-panel";
import { SaveIndicator, type SaveState } from "./builder/save-indicator";
import { OutlineRail } from "./builder/outline-rail";
import { CanvasStage } from "./builder/canvas-stage";
import { RestyleInspector } from "./builder/restyle-inspector";
import { ElementsInspector } from "./builder/elements-inspector";
import { AiChatPanel } from "./builder/ai-chat-panel";
import { InsightsPanel } from "./builder/insights-panel";
import { ListEditPanel } from "./builder/list-edit-panel";
import {
  buildEditableContent,
  parseEditPath,
  applyTextEdit,
  applyStructuralEdit,
  themeForTemplate,
  type CvDocumentEditing,
  type CvEdit,
  type PartialCvTheme,
} from "@/components/cv/render";
import type { FontPairingKey } from "@/components/cv/render/palettes";
import { FONT_PAIRINGS } from "@/components/cv/render/palettes";
import { CvPhotoEditor, type PhotoShape } from "./builder/cv-photo-editor";
import {
  ApiError,
  cvApi,
  parseCvQuotaError,
  patchElementStyle,
  profileApi,
  readImportOrigin,
  resolveDownloadUrl,
  type CvCanvasTheme,
  type CvLinkType,
  type CvQuotaInfo,
  type CvSection,
  type CvSectionContent,
  type ElementStyle,
  type ElementStyleMap,
  type ImportOrigin,
} from "@/lib/api";
import { sectionTypeKey } from "@/lib/cv/sections";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

const AUTOSAVE_DELAY_MS = 1200;

export function CvBuilderScreen({ cvId, initialSuggestionId, jobId }: { cvId: string; initialSuggestionId?: string; jobId?: string }) {
  const t = useTranslations("cv");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const toast = useToast();
  const apiError = useApiErrorMessage();
  const queryClient = useQueryClient();
  const router = useRouter();

  const query = useQuery({
    queryKey: ["cv", "detail", cvId],
    queryFn: () => cvApi.get(cvId),
    retry: false,
  });

  // ---- Local working copy (single source for editor + live A4 canvas) ----
  const [sections, setSections] = useState<CvSection[]>([]);
  const [title, setTitle] = useState("");
  const [templateId, setTemplateId] = useState<string>("");
  // Per-CV theme overrides (palette/typography/density), layered on the template.
  const [canvasTheme, setCanvasTheme] = useState<CvCanvasTheme | null>(null);
  // Per-element style overrides (contextual text toolbar), keyed by edit-path.
  const [elementStyles, setElementStyles] = useState<ElementStyleMap>({});
  // The `data-edit-path` currently selected for styling (anchors the toolbar).
  const [activeStylePath, setActiveStylePath] = useState<string | null>(null);
  // Right-inspector tab (desktop): design / elements / ai / versions.
  const [inspectorTab, setInspectorTab] = useState("design");
  const [selectedSectionId, setSelectedSectionId] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [liveVersion, setLiveVersion] = useState(0);
  const [conflict, setConflict] = useState(false);
  const [mobileTab, setMobileTab] = useState("canvas");
  const [exportOpen, setExportOpen] = useState(false);
  const [restoringId, setRestoringId] = useState<string | null>(null);
  const [addingSection, setAddingSection] = useState(false);
  // Drag-to-reorder (pointer) state for the list-edit fallback.
  const [armedId, setArmedId] = useState<string | null>(null);
  const [dragId, setDragId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);
  // Best-effort original-document link for imported CVs (session-scoped).
  const [origin, setOrigin] = useState<ImportOrigin | null>(null);

  // ---- Photo editor state ----
  const [photoOpen, setPhotoOpen] = useState(false);
  const [photoSaving, setPhotoSaving] = useState(false);

  // ---- Lifecycle: "Save to library" (finalize a draft → ready) ----
  // Local status mirror so the pill/button flip immediately on success without
  // waiting for a full detail refetch. Hydrated from the server detail below.
  const [status, setStatus] = useState<string>("draft");
  const [finalizing, setFinalizing] = useState(false);
  const [finalizeError, setFinalizeError] = useState<string | null>(null);
  const [quotaInfo, setQuotaInfo] = useState<CvQuotaInfo | null>(null);

  const sectionsRef = useRef<CvSection[]>([]);
  const titleRef = useRef("");
  const canvasThemeRef = useRef<CvCanvasTheme | null>(null);
  const elementStylesRef = useRef<ElementStyleMap>({});
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

  // The student's own profile — only needed for the "use system avatar" action.
  const profile = useQuery({
    queryKey: ["profile", "me", "avatar"],
    queryFn: () => profileApi.getMine(),
    staleTime: 5 * 60_000,
    retry: false,
  });

  // Keep refs in sync with state for use inside the async save queue.
  useEffect(() => {
    sectionsRef.current = sections;
  }, [sections]);
  useEffect(() => {
    titleRef.current = title;
  }, [title]);
  useEffect(() => {
    canvasThemeRef.current = canvasTheme;
  }, [canvasTheme]);
  useEffect(() => {
    elementStylesRef.current = elementStyles;
  }, [elementStyles]);

  // Hydrate local state from the server on first load and after conflict reload.
  const data = query.data;
  useEffect(() => {
    if (!data) return;
    if (hydratedRef.current === data.id && !forceHydrateRef.current) return;
    setSections(data.sections);
    setTitle(data.title);
    setStatus(data.status);
    setTemplateId(data.template_id ?? "");
    setCanvasTheme((data.canvas?.theme as CvCanvasTheme | null | undefined) ?? null);
    setElementStyles((data.canvas?.elementStyles as ElementStyleMap | null | undefined) ?? {});
    versionRef.current = data.version;
    setLiveVersion(data.version);
    hydratedRef.current = data.id;
    forceHydrateRef.current = false;
    setSaveState("idle");
  }, [data]);

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
    (patch: { title?: string; template_id?: string | null }) =>
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

  // Persist the per-CV theme override (palette/typography/density). Discrete
  // restyle actions commit immediately — no debounce.
  const persistTheme = useCallback(
    (theme: CvCanvasTheme) =>
      enqueue(async () => {
        setSaveState("saving");
        try {
          const res = await cvApi.updateCanvas(cvId, {
            theme,
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

  // Persist the per-element style map (contextual text toolbar). Sent as the
  // FULL map via the canvas PATCH (sibling of `theme`); optimistic + versioned.
  const persistElementStyles = useCallback(
    (map: ElementStyleMap) =>
      enqueue(async () => {
        setSaveState("saving");
        try {
          const res = await cvApi.updateCanvas(cvId, {
            elementStyles: map,
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

  // Apply a single-key style patch to the active element, optimistically, then
  // persist the merged full map (design spec §4 contextual toolbar).
  const handleStylePatch = useCallback(
    (patch: ElementStyle) => {
      const path = activeStylePath;
      if (!path) return;
      const next = patchElementStyle(elementStylesRef.current, path, patch);
      setElementStyles(next);
      void persistElementStyles(next);
    },
    [activeStylePath, persistElementStyles],
  );

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

  // Fetch the profile avatar → File → upload as the CV photo (design spec §6.4).
  const applySystemAvatar = useCallback(
    async (shape: PhotoShape) => {
      const url = profile.data?.avatar_url;
      if (!url) return;
      setPhotoSaving(true);
      try {
        const res = await fetch(resolveDownloadUrl(url), { credentials: "include" });
        if (!res.ok) throw new Error("avatar-fetch-failed");
        const blob = await res.blob();
        const ext = blob.type.includes("png") ? "png" : blob.type.includes("webp") ? "webp" : "jpg";
        const file = new File([blob], `avatar.${ext}`, {
          type: blob.type || "image/jpeg",
        });
        await persistPhoto({
          file,
          cropX: 0,
          cropY: 0,
          cropWidth: 1,
          cropHeight: 1,
          shape,
        });
      } catch {
        setPhotoSaving(false);
        toast.show({ tone: "error", title: t("canvas.systemAvatarError") });
      }
    },
    [profile.data?.avatar_url, persistPhoto, toast, t],
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
  const changeSectionContent = useCallback(
    (sectionId: string, content: CvSectionContent) => {
      setSections((prev) =>
        prev.map((s) => (s.id === sectionId ? { ...s, content } : s)),
      );
      scheduleAutosave(sectionId);
    },
    [scheduleAutosave],
  );

  // The `header` section id (used to resolve `header.*` edit paths).
  const headerSectionId = useMemo(
    () => sections.find((s) => s.section_type === "header")?.id ?? null,
    [sections],
  );

  // ---- Inline canvas text commit (debounced input + blur) ----
  const handleEditCommit = useCallback(
    (path: string, value: string) => {
      const target = parseEditPath(path);
      if (!target) return;
      const sectionId =
        target.kind.startsWith("header.")
          ? headerSectionId
          : "sectionId" in target
            ? target.sectionId
            : null;
      if (!sectionId) return;
      const current = sectionsRef.current.find((s) => s.id === sectionId);
      if (!current) return;
      const nextContent = applyTextEdit(current.content ?? {}, target, value);
      if (nextContent === current.content) return;
      changeSectionContent(sectionId, nextContent);
    },
    [headerSectionId, changeSectionContent],
  );

  // ---- On-canvas structural edits (add/remove entry/highlight/item, level) ----
  const handleStructuralEdit = useCallback(
    (edit: CvEdit) => {
      const sectionId =
        edit.kind === "add-link" || edit.kind === "remove-link"
          ? headerSectionId
          : "sectionId" in edit
            ? edit.sectionId
            : null;
      if (!sectionId) return;
      const current = sectionsRef.current.find((s) => s.id === sectionId);
      if (!current) return;
      const nextContent = applyStructuralEdit(current.content ?? {}, edit);
      setSections((prev) =>
        prev.map((s) => (s.id === sectionId ? { ...s, content: nextContent } : s)),
      );
      // Skill-level drags fire often; debounce. Add/remove commit immediately.
      if (edit.kind === "set-skill-level") scheduleAutosave(sectionId);
      else flushSection(sectionId);
    },
    [headerSectionId, scheduleAutosave, flushSection],
  );

  const toggleVisible = useCallback(
    (sectionId: string, visible: boolean) => {
      setSections((prev) =>
        prev.map((s) => (s.id === sectionId ? { ...s, is_visible: visible } : s)),
      );
      flushSection(sectionId);
    },
    [flushSection],
  );

  const moveSection = useCallback(
    (sectionId: string, direction: "up" | "down") => {
      // Compute from the live ref (kept in sync) so persistence side-effects
      // happen exactly once — never inside the state updater (StrictMode-safe).
      const prev = sectionsRef.current;
      const idx = prev.findIndex((s) => s.id === sectionId);
      const j = direction === "up" ? idx - 1 : idx + 1;
      if (idx < 0 || j < 0 || j >= prev.length) return;
      const a = prev[idx]!;
      const b = prev[j]!;
      const next = [...prev];
      next[idx] = { ...b, sort_order: a.sort_order };
      next[j] = { ...a, sort_order: b.sort_order };
      setSections(next);
      // Persist both (serialized; version advances between writes).
      void persistSection(a.id);
      void persistSection(b.id);
    },
    [persistSection],
  );

  // Drag-to-reorder (list-edit fallback): move `dragId` to `targetId`,
  // renumber sort_order densely, persist rows whose order changed.
  const dropOnto = useCallback(
    (targetId: string) => {
      if (!dragId || dragId === targetId) return;
      const prev = sectionsRef.current;
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
    },
    [dragId, persistSection],
  );

  function handleTitleChange(value: string) {
    setTitle(value);
  }
  function flushTitle() {
    if (titleRef.current.trim() && titleRef.current !== data?.title) {
      void persistMeta({ title: titleRef.current.trim() });
    }
  }

  const handleTemplateChange = useCallback(
    (value: string) => {
      setTemplateId(value);
      void persistMeta({ template_id: value || null });
    },
    [persistMeta],
  );

  // ---- Restyle handlers (optimistic local theme + persist) ----
  const mergeTheme = useCallback(
    (patch: CvCanvasTheme) => {
      const merged: CvCanvasTheme = {
        ...canvasThemeRef.current,
        ...patch,
        palette: { ...canvasThemeRef.current?.palette, ...patch.palette },
        typography: { ...canvasThemeRef.current?.typography, ...patch.typography },
        sectionStyle: { ...canvasThemeRef.current?.sectionStyle, ...patch.sectionStyle },
      };
      setCanvasTheme(merged);
      void persistTheme(merged);
    },
    [persistTheme],
  );

  const handlePaletteChange = useCallback(
    (palette: Record<string, string>) => mergeTheme({ palette }),
    [mergeTheme],
  );
  const handleAccentChange = useCallback(
    (accent: string) => mergeTheme({ palette: { accent } }),
    [mergeTheme],
  );
  const handleFontChange = useCallback(
    (pairing: FontPairingKey) => {
      const p = FONT_PAIRINGS.find((f) => f.key === pairing);
      if (!p) return;
      mergeTheme({ typography: { headingFont: p.headingFont, bodyFont: p.bodyFont } });
    },
    [mergeTheme],
  );
  const handleDensityChange = useCallback(
    // Density tunes both the overall type scale (comfortable/compact) and the
    // per-entry gap (`sectionStyle.itemGap`), per design spec §6 "Density".
    (scale: "regular" | "compact") =>
      mergeTheme({
        typography: { scale },
        sectionStyle: { itemGap: scale === "compact" ? "tight" : "regular" },
      }),
    [mergeTheme],
  );

  // Append a section of the given type with a sensible starter content shape.
  // `entrySeed` sections open an empty entry; `skills`/`languages` open one
  // level item; `text` sections open an empty paragraph; a divider carries the
  // presentation-only `{ divider: true }` marker.
  const addSectionOfType = useCallback(
    async (
      sectionType: string,
      opts?: { title?: string; content?: CvSectionContent; toastKey?: string },
    ) => {
      setAddingSection(true);
      try {
        const sectionTypeKeyName = `sectionTypes.${sectionTypeKey(sectionType)}`;
        const defaultTitle = t.has(sectionTypeKeyName)
          ? t(sectionTypeKeyName)
          : t("builder.newSectionTitle");
        const res = await cvApi.addSection(cvId, {
          section_type: sectionType,
          title: opts?.title ?? defaultTitle,
          is_visible: true,
          content: opts?.content ?? { items: [] },
          expected_version: versionRef.current,
        });
        versionRef.current = res.cv_version;
        forceHydrateRef.current = true;
        await query.refetch();
        setSelectedSectionId(res.section.id);
        toast.show({
          tone: "success",
          title: opts?.toastKey ? t(opts.toastKey) : t("builder.sectionAdded"),
        });
      } catch (e) {
        if (e instanceof ApiError && e.code === "CONFLICT") {
          await handleConflict();
        } else {
          toast.show({ tone: "error", title: apiError(e) });
        }
      } finally {
        setAddingSection(false);
      }
    },
    [cvId, t, query, toast, apiError, handleConflict],
  );

  const handleAddSection = useCallback(
    () => addSectionOfType("custom"),
    [addSectionOfType],
  );

  const handleAddSectionOfType = useCallback(
    (sectionType: string) => {
      // Seed a first row so the fresh section is immediately editable on-canvas.
      const seed: CvSectionContent =
        sectionType === "skills" || sectionType === "languages"
          ? { items: [{ name: "", level: 70 }] }
          : sectionType === "summary"
            ? { text: "" }
            : ["experience", "education", "projects", "certifications", "awards", "activities"].includes(
                  sectionType,
                )
              ? { entries: [{ heading: "", highlights: [] }] }
              : { items: [] };
      void addSectionOfType(sectionType, { content: seed });
    },
    [addSectionOfType],
  );

  const handleAddSkillBar = useCallback(
    () =>
      void addSectionOfType("skills", {
        content: { items: [{ name: "", level: 70 }] },
      }),
    [addSectionOfType],
  );

  const handleAddCustomField = useCallback(
    () =>
      void addSectionOfType("custom", {
        title: t("elements.customFieldTitle"),
        content: { items: [{ text: "" }] },
      }),
    [addSectionOfType, t],
  );

  const handleAddDivider = useCallback(
    () =>
      void addSectionOfType("custom", {
        title: t("elements.divider"),
        content: { divider: true },
        toastKey: "elements.dividerAdded",
      }),
    [addSectionOfType, t],
  );

  // Add a typed contact link (LinkedIn / GitHub / …) to the header section so
  // the renderer draws the matching icon (design spec §3 Elements customization).
  const handleAddTypedLink = useCallback(
    (link: { type: CvLinkType; label: string }) => {
      const sectionId = sectionsRef.current.find((s) => s.section_type === "header")?.id;
      if (!sectionId) return;
      const current = sectionsRef.current.find((s) => s.id === sectionId);
      if (!current) return;
      const nextContent = applyStructuralEdit(current.content ?? {}, {
        kind: "add-link",
        type: link.type,
        label: link.label,
      });
      setSections((prev) =>
        prev.map((s) => (s.id === sectionId ? { ...s, content: nextContent } : s)),
      );
      flushSection(sectionId);
      toast.show({ tone: "success", title: t("elements.linkAdded", { label: link.label }) });
    },
    [flushSection, toast, t],
  );

  const handleRestore = useCallback(
    async (versionId: string) => {
      setRestoringId(versionId);
      try {
        const restored = await cvApi.restoreVersion(cvId, versionId, versionRef.current);
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
    },
    [cvId, query, toast, apiError, handleConflict, t],
  );

  // ---- Commit this draft CV to the library (finalize → ready) ----
  // Flushes any pending section autosave first so the finalize validation and
  // snapshot capture the latest edits. On quota-full → recovery dialog; on the
  // user-safe empty-CV error → inline block (never crashes the editor).
  const handleFinalize = useCallback(async () => {
    setFinalizeError(null);
    setFinalizing(true);
    // Wait for the in-flight autosave queue to settle so the server has the
    // student's latest content before it validates non-empty + snapshots.
    try {
      await queueRef.current;
    } catch {
      /* autosave surfaces its own error; finalize still proceeds. */
    }
    try {
      const detail = await cvApi.finalize(cvId);
      versionRef.current = detail.version;
      setLiveVersion(detail.version);
      setStatus(detail.status);
      toast.show({
        tone: "success",
        title: t("builder.finalizeSuccessTitle"),
        description: t("builder.finalizeSuccessBody"),
      });
      // Refresh the library list (quota + section membership) and the cached detail.
      queryClient.setQueryData(["cv", "detail", cvId], detail);
      void queryClient.invalidateQueries({ queryKey: ["cv", "list"] });
    } catch (e) {
      const quota = parseCvQuotaError(e);
      if (quota) {
        setQuotaInfo(quota);
      } else if (e instanceof ApiError) {
        // Prefer localized FRONTEND copy keyed by the backend `reason` code so
        // the /en page never renders the backend's Vietnamese default message.
        const reason =
          typeof e.details?.reason === "string" ? (e.details.reason as string) : undefined;
        const reasonKey = reason ? `builder.finalizeReason.${reason}` : undefined;
        if (reasonKey && t.has(reasonKey)) {
          setFinalizeError(t(reasonKey));
        } else {
          setFinalizeError(e.message);
        }
      } else {
        setFinalizeError(apiError(e));
      }
    } finally {
      setFinalizing(false);
    }
  }, [cvId, queryClient, toast, t, apiError]);

  // ---------------------------- Render states ----------------------------
  if (query.isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-40" />
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(340px,420px)]">
          <Skeleton className="h-[560px] w-full rounded-2xl" />
          <div className="hidden space-y-4 lg:block">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-36 w-full rounded-2xl" />
            ))}
          </div>
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
  const versionId = detail.current_version_id ?? detail.versions?.[0]?.id ?? null;
  // Lifecycle: `ready` = committed to the library (analyzed, usable to apply);
  // `draft` = unlimited scratch. Read from the local mirror so the pill/button
  // flip immediately after finalize.
  const isReady = status === "ready";

  const sectionLabel = (s: CvSection) => {
    const key = `sectionTypes.${sectionTypeKey(s.section_type)}`;
    return t.has(key) ? t(key) : s.title;
  };
  const visibleCount = sections.filter((s) => s.is_visible).length;
  const activeTemplate = templates.data?.find((tpl) => tpl.id === templateId) ?? null;
  const activeTemplateName = activeTemplate?.name ?? null;
  const canvasPhoto = detail.canvas?.photo ?? null;

  // ---- Resolve the theme (template + per-CV overrides) and build content. ----
  const previewTheme = themeForTemplate(
    activeTemplate,
    (canvasTheme ?? undefined) as PartialCvTheme,
  );
  const editableContent = buildEditableContent(sections, title || t("preview.untitled"));
  if (canvasPhoto?.url) editableContent.photo = { url: canvasPhoto.url };

  const showsPhoto = previewTheme.photo.show;
  const hasSystemAvatar = Boolean(profile.data?.avatar_url);

  const saveIndicator = <SaveIndicator state={saveState} />;

  // ---- Editing wiring passed to the editable <CvDocument/>. ----
  const editing: CvDocumentEditing = {
    selectedSectionId,
    onEditCommit: handleEditCommit,
    onSelectSection: setSelectedSectionId,
    onEdit: handleStructuralEdit,
    onMoveSection: moveSection,
    activeStylePath,
    onActiveStylePathChange: (path) => setActiveStylePath(path),
    labels: {
      placeholderName: t("canvasEdit.name"),
      placeholderHeadline: t("canvasEdit.headline"),
      placeholderEmail: t("canvasEdit.email"),
      placeholderPhone: t("canvasEdit.phone"),
      placeholderLocation: t("canvasEdit.location"),
      placeholderLinkLabel: t("canvasEdit.linkLabel"),
      placeholderLinkUrl: t("canvasEdit.linkUrl"),
      placeholderHeading: t("canvasEdit.heading"),
      placeholderSubheading: t("canvasEdit.subheading"),
      placeholderTimeframe: t("canvasEdit.timeframe"),
      placeholderEntryLocation: t("canvasEdit.entryLocation"),
      placeholderNote: t("canvasEdit.note"),
      placeholderHighlight: t("canvasEdit.highlight"),
      placeholderText: t("canvasEdit.text"),
      placeholderSkill: t("canvasEdit.skill"),
      addHighlight: t("canvasEdit.addHighlight"),
      addEntry: t("canvasEdit.addEntry"),
      addItem: t("canvasEdit.addItem"),
      removeHighlight: t("canvasEdit.removeHighlight"),
      removeEntry: t("canvasEdit.removeEntry"),
      removeItem: t("canvasEdit.removeItem"),
      moveSectionUp: t("editor.moveUp"),
      moveSectionDown: t("editor.moveDown"),
      skillLevel: t("canvasEdit.skillLevel"),
      editField: (name: string) => t("canvasEdit.editField", { name }),
    },
  };

  const photoControl = showsPhoto ? (
    <Button variant="secondary" size="sm" onClick={() => setPhotoOpen(true)}>
      <ImageSquare aria-hidden weight="duotone" className="size-4" />
      {canvasPhoto?.url ? t("canvas.editPhoto") : t("canvas.addPhoto")}
    </Button>
  ) : null;

  // ---- The central editing canvas. ----
  const canvasPanel = (
    <div className="space-y-4">
      {/* CV name — small metadata edit stays a labelled input (not on-canvas). */}
      <div className="flex flex-col gap-2 rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] p-3 shadow-[var(--shadow-sm)] backdrop-blur-md sm:flex-row sm:items-center">
        <label htmlFor="cv-title" className="shrink-0 text-xs font-semibold text-[var(--text-muted)]">
          {t("builder.titleLabel")}
        </label>
        <input
          id="cv-title"
          value={title}
          onChange={(e) => handleTitleChange(e.target.value)}
          onBlur={flushTitle}
          className="w-full rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] px-3 py-2 text-sm font-medium text-[var(--text-primary)] outline-none backdrop-blur-sm transition-colors focus:border-[var(--brand-primary)]/50 focus:bg-[var(--glass-surface-heavy)] focus:ring-2 focus:ring-[var(--brand-primary)]/30"
        />
      </div>

      <CanvasStage
        content={editableContent}
        theme={previewTheme}
        editing={editing}
        photoControl={photoControl}
        elementStyles={elementStyles}
        activeStylePath={activeStylePath}
        activeStyle={activeStylePath ? elementStyles[activeStylePath] : undefined}
        onStylePatch={handleStylePatch}
        onCloseToolbar={() => setActiveStylePath(null)}
      />

      {/* List-edit fallback: full keyboard/bulk editing, collapsed by default. */}
      <ListEditPanel
        sections={sections}
        addingSection={addingSection}
        drag={{ armedId, dragId, overId, setArmedId, setDragId, setOverId, dropOnto }}
        onContentChange={changeSectionContent}
        onFlush={flushSection}
        onToggleVisible={toggleVisible}
        onMove={moveSection}
        onAddSection={handleAddSection}
      />
    </div>
  );

  const onAiApplied = () => {
    forceHydrateRef.current = true;
    void query.refetch();
  };

  // ---- Tab: Design (Restyle + photo). ----
  const designPanel = (
    <div className="space-y-4">
      <RestyleInspector
        templates={templates.data ?? []}
        templatesLoading={templates.isPending}
        activeTemplateId={templateId}
        canvasTheme={canvasTheme}
        onSelectTemplate={handleTemplateChange}
        onPaletteChange={handlePaletteChange}
        onAccentChange={handleAccentChange}
        onFontChange={handleFontChange}
        onDensityChange={handleDensityChange}
      />
      {showsPhoto && (
        <div className="rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] p-4 shadow-[var(--shadow-sm)] backdrop-blur-md">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("canvas.photo")}
          </p>
          <Button variant="secondary" size="sm" fullWidth onClick={() => setPhotoOpen(true)}>
            <ImageSquare aria-hidden weight="duotone" className="size-4" />
            {canvasPhoto?.url ? t("canvas.editPhoto") : t("canvas.addPhoto")}
          </Button>
        </div>
      )}
    </div>
  );

  // ---- Tab: Elements (customization: typed links, blocks, add-section). ----
  const elementsPanel = (
    <div className="space-y-4">
      <ElementsInspector
        hasHeader={headerSectionId !== null}
        addingSection={addingSection}
        onAddLink={handleAddTypedLink}
        onAddSection={handleAddSectionOfType}
        onAddDivider={handleAddDivider}
        onAddSkillBar={handleAddSkillBar}
        onAddCustomField={handleAddCustomField}
      />
      <InsightsPanel cvId={cvId} jobId={jobId} sections={sections} />
    </div>
  );

  // ---- Tab: AI (integrated chat assistant). ----
  const aiPanel = (
    <div className="space-y-4">
      <AiChatPanel
        cvId={cvId}
        sections={sections}
        jobId={jobId}
        initialSuggestionId={initialSuggestionId}
        selectedSectionId={selectedSectionId}
        onApplied={onAiApplied}
      />
    </div>
  );

  // ---- Tab: Versions (timeline + restore) + original-upload link. ----
  const versionsPanel = (
    <div className="space-y-4">
      <VersionsPanel
        version={liveVersion}
        lastEditedAt={detail.last_edited_at}
        versions={detail.versions}
        onRestore={handleRestore}
        restoringId={restoringId}
      />
      {origin && origin.previewUrl && (
        <div className="rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] p-3.5 shadow-[var(--shadow-sm)] backdrop-blur-md">
          <p className="mb-1.5 text-xs font-bold uppercase tracking-wide text-[var(--text-muted)]">
            {t("builder.originalTitle")}
          </p>
          <div className="flex items-center gap-2.5">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg icon-chip-primary shadow-sm">
              <FileArrowUp aria-hidden weight="duotone" className="size-5 text-white" />
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
    </div>
  );

  const inspectorTabItems = [
    {
      value: "design",
      label: t("builder.tabDesign"),
      icon: <PaintBrushBroad aria-hidden weight="duotone" className="size-4" />,
    },
    {
      value: "elements",
      label: t("builder.tabElements"),
      icon: <PuzzlePiece aria-hidden weight="duotone" className="size-4" />,
    },
    {
      value: "ai",
      label: t("builder.tabAi"),
      icon: <Sparkle aria-hidden weight="duotone" className="size-4" />,
    },
    {
      value: "versions",
      label: t("builder.tabVersions"),
      icon: <ClockCounterClockwise aria-hidden weight="duotone" className="size-4" />,
    },
  ];

  const inspectorPanels: Record<string, React.ReactNode> = {
    design: designPanel,
    elements: elementsPanel,
    ai: aiPanel,
    versions: versionsPanel,
  };

  // Left outline rail (desktop lg+). Keyboard path for select/reorder/hide.
  const outlineRail = (
    <OutlineRail
      sections={sections}
      visibleCount={visibleCount}
      activeTemplateName={activeTemplateName}
      addingSection={addingSection}
      selectedSectionId={selectedSectionId}
      sectionLabel={sectionLabel}
      onSelect={setSelectedSectionId}
      onMove={moveSection}
      onToggleVisible={toggleVisible}
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
          {isReady ? (
            <StatusBadge tone="verified">
              <CheckCircle aria-hidden weight="fill" className="size-3.5" />
              {t("status.ready")}
            </StatusBadge>
          ) : (
            <StatusBadge tone="draft">{t("status.draft")}</StatusBadge>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          {saveIndicator}
          {isReady ? (
            <span className="hidden items-center gap-1 text-xs font-medium text-[var(--text-muted)] sm:inline-flex">
              <CheckCircle
                aria-hidden
                weight="fill"
                className="size-3.5 text-[var(--brand-teal)]"
              />
              {t("builder.inLibrary")}
            </span>
          ) : (
            <Button
              variant="primary"
              loading={finalizing}
              onClick={() => void handleFinalize()}
            >
              <FloppyDisk aria-hidden weight="bold" className="size-4" />
              {finalizing ? t("builder.finalizing") : t("builder.saveToLibrary")}
            </Button>
          )}
          <Button variant="secondary" onClick={() => setExportOpen(true)}>
            <DownloadSimple aria-hidden weight="bold" className="size-4" />
            {t("builder.export")}
          </Button>
        </div>
      </div>

      {finalizeError && (
        <div
          role="alert"
          className="mb-4 flex items-start gap-3 rounded-xl border border-[var(--amber-600)]/40 bg-[var(--amber-100)] p-3.5"
        >
          <span className="flex size-7 shrink-0 items-center justify-center rounded-lg icon-chip-warning shadow-sm">
            <WarningCircle aria-hidden weight="duotone" className="size-4 text-white" />
          </span>
          <div className="flex-1">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {t("builder.finalizeBlockedTitle")}
            </p>
            <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
              {finalizeError}
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={() => setFinalizeError(null)}>
            {tc("close")}
          </Button>
        </div>
      )}

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

      {/* Mobile tabs: Canvas + the four inspector tabs. The canvas panel and the
          inspector share one tab bar on small screens; on desktop the canvas is
          always visible and the inspector has its own tab bar (below). */}
      <div className="lg:hidden">
        <Tabs
          ariaLabel={t("builder.tabsLabel")}
          value={mobileTab}
          onValueChange={setMobileTab}
          idBase="cv-builder-mobile"
          items={[
            {
              value: "canvas",
              label: t("builder.tabCanvas"),
              icon: <Rows aria-hidden weight="duotone" className="size-4" />,
            },
            ...inspectorTabItems,
          ]}
        />
      </div>

      {/* Desktop: outline / canvas / tabbed inspector side-by-side. */}
      <div className="mt-4 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(340px,400px)] lg:gap-5 xl:grid-cols-[220px_minmax(0,1fr)_minmax(360px,420px)]">
        {outlineRail}

        {/* Canvas: always visible on desktop; on mobile only when its tab is active. */}
        <div className={mobileTab === "canvas" ? "block lg:block" : "hidden lg:block"}>
          {canvasPanel}
        </div>

        {/* Right inspector column. */}
        <div>
          {/* Desktop inspector tab bar. */}
          <div className="hidden lg:block">
            <Tabs
              ariaLabel={t("builder.inspectorTabsLabel")}
              value={inspectorTab}
              onValueChange={setInspectorTab}
              idBase="cv-builder-inspector"
              className="mb-4"
              items={inspectorTabItems}
            />
            <TabPanel tabsId="cv-builder-inspector" value={inspectorTab} active>
              {inspectorPanels[inspectorTab]}
            </TabPanel>
          </div>

          {/* Mobile inspector panels — driven by the shared mobile tab. */}
          <div className="lg:hidden">
            {mobileTab !== "canvas" && inspectorPanels[mobileTab]}
          </div>
        </div>
      </div>

      <CvExportModal
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        cvId={cvId}
        versionId={versionId}
      />

      <CvQuotaModal
        open={quotaInfo !== null}
        info={quotaInfo}
        onClose={() => setQuotaInfo(null)}
        onGoToLibrary={() => {
          setQuotaInfo(null);
          router.push("/student/cv");
        }}
      />

      <CvPhotoEditor
        open={photoOpen}
        onClose={() => setPhotoOpen(false)}
        currentPhoto={canvasPhoto}
        saving={photoSaving}
        systemAvatarAvailable={hasSystemAvatar}
        onUseSystemAvatar={(shape) => void applySystemAvatar(shape)}
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
