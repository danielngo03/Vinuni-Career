"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  CheckCircle,
  FilePlus,
  FileText,
  PencilLine,
  SignIn,
  UploadSimple,
  WarningCircle,
} from "@phosphor-icons/react";
import { useRouter } from "@/i18n/navigation";
import { Button, EmptyState, Modal, Skeleton, useToast } from "@/components/ui";
import { CvCreateModal } from "./cv-create-modal";
import { CvQuotaModal } from "./cv-quota-modal";
import { CvStudioHeader } from "./studio/cv-studio-header";
import { TemplateShelf } from "./studio/template-shelf";
import { QuotaStrip } from "./studio/quota-strip";
import { CvLibraryCard } from "./studio/cv-library-card";
import {
  ApiError,
  cvApi,
  newIdempotencyKey,
  parseCvQuotaError,
  type CvDetail,
  type CvSummary,
  type CvQuotaInfo,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

export function CvStudioScreen() {
  const t = useTranslations("cv");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const router = useRouter();
  const searchParams = useSearchParams();
  const toast = useToast();
  const apiError = useApiErrorMessage();
  const queryClient = useQueryClient();

  const [createOpen, setCreateOpen] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [quotaInfo, setQuotaInfo] = useState<CvQuotaInfo | null>(null);
  const [shelfTemplateId, setShelfTemplateId] = useState<string | null>(null);
  const [deleteCandidate, setDeleteCandidate] = useState<CvSummary | null>(null);

  // The import flow's "start from template" recovery returns here with ?create=1.
  useEffect(() => {
    if (searchParams.get("create") === "1") {
      setCreateOpen(true);
      router.replace("/student/cv");
    }
  }, [searchParams, router]);

  const templates = useQuery({
    queryKey: ["cv", "templates"],
    queryFn: () => cvApi.listTemplates(),
    staleTime: 5 * 60_000,
  });

  const query = useInfiniteQuery({
    queryKey: ["cv", "list"],
    queryFn: ({ pageParam }) => cvApi.list({ cursor: pageParam, limit: 20 }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.page.next_cursor,
    retry: false,
  });

  const rows: CvSummary[] = useMemo(
    () => query.data?.pages.flatMap((p) => p.data) ?? [],
    [query.data],
  );

  // Two lifecycle tiers: the library (analyzed, quota-bound `ready` CVs, usable
  // to apply + job-fit) and unlimited free-form drafts (not counted).
  const readyRows = useMemo(
    () => rows.filter((cv) => cv.status === "ready"),
    [rows],
  );
  const draftRows = useMemo(
    () => rows.filter((cv) => cv.status === "draft"),
    [rows],
  );

  // Quota meta is identical across pages; read it from the first fetched page.
  const meta = query.data?.pages[0]?.meta ?? null;
  // Only Upload is quota-gated now (an uploaded CV lands in the library). Drafts
  // (New CV / template / duplicate) are unlimited and never quota-disabled.
  const canUpload = meta?.can_create ?? true;
  const limitHint = meta
    ? t("quota.disabledHint", { limit: meta.active_cv_limit })
    : undefined;

  function goToBuilder(cv: CvDetail | CvSummary) {
    const suggestion = (cv as CvDetail).pending_suggestion;
    const params = suggestion?.suggestion_id ? `?suggest=${suggestion.suggestion_id}` : "";
    router.push(`/student/cv/${cv.id}${params}`);
  }

  function startFromTemplate(id: string | null) {
    setShelfTemplateId(id);
    setCreateOpen(true);
  }

  function refetchList() {
    void queryClient.invalidateQueries({ queryKey: ["cv", "list"] });
  }

  async function duplicate(cv: CvSummary) {
    setBusyId(cv.id);
    try {
      const dup = await cvApi.duplicate(cv.id, {
        title: t("list.copyTitle", { title: cv.title }),
        idempotency_key: newIdempotencyKey(),
      });
      toast.show({ tone: "success", title: t("list.duplicatedToast") });
      goToBuilder(dup);
    } catch (e) {
      const quota = parseCvQuotaError(e);
      if (quota) {
        setQuotaInfo(quota);
        return;
      }
      toast.show({ tone: "error", title: apiError(e) });
    } finally {
      setBusyId(null);
    }
  }

  async function remove(cv: CvSummary) {
    setBusyId(cv.id);
    try {
      await cvApi.remove(cv.id);
      toast.show({ tone: "success", title: t("list.deletedToast") });
      setDeleteCandidate(null);
      refetchList();
    } catch (e) {
      toast.show({ tone: "error", title: apiError(e) });
    } finally {
      setBusyId(null);
    }
  }

  function goToLibrary() {
    setQuotaInfo(null);
    if (typeof document !== "undefined") {
      document
        .getElementById("cv-library")
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  const headerActions = (
    <>
      <Button
        variant="secondary"
        onClick={() => router.push("/student/cv/import")}
        disabled={!canUpload}
        title={!canUpload ? limitHint : undefined}
      >
        <UploadSimple aria-hidden weight="bold" className="size-4" />
        {t("list.upload")}
      </Button>
      <Button variant="primary" onClick={() => setCreateOpen(true)}>
        <FilePlus aria-hidden weight="bold" className="size-4" />
        {t("list.newCv")}
      </Button>
    </>
  );

  const quotaStrip = <QuotaStrip meta={meta} />;

  const templateShelf = (
    <TemplateShelf templates={templates.data ?? []} onSelect={startFromTemplate} />
  );

  // Auth state.
  if (
    query.isError &&
    query.error instanceof ApiError &&
    query.error.isAuthError
  ) {
    return (
      <>
        <CvStudioHeader title={t("list.title")} description={t("list.subtitle")} />
        <EmptyState
          kind="auth"
          icon={SignIn}
          title={tStates("authTitle")}
          description={tStates("authBody")}
        />
      </>
    );
  }

  return (
    <>
      <CvStudioHeader
        title={t("list.title")}
        description={t("list.subtitle")}
        sideTitle={t("list.headerSideTitle")}
        sideBody={t("list.headerSideBody")}
        actions={headerActions}
      />

      {query.isPending ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="marketplace-card rounded-[14px] p-5"
            >
              <Skeleton className="h-5 w-2/3" />
              <Skeleton className="mt-3 h-4 w-1/3" />
              <Skeleton className="mt-6 h-9 w-full" />
            </div>
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
      ) : rows.length === 0 ? (
        <EmptyState
          kind="empty"
          icon={FileText}
          title={t("list.emptyTitle")}
          description={t("list.emptyBody")}
          action={
            <div className="flex flex-wrap justify-center gap-2">
              {headerActions}
            </div>
          }
        />
      ) : (
        <>
          {templateShelf}

          {/* ── Library: analyzed, quota-bound `ready` CVs (apply + job-fit) ── */}
          <section id="cv-library" className="scroll-mt-24">
            <div className="mb-2.5 flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
              <h2 className="flex items-center gap-1.5 text-sm font-bold text-[var(--text-primary)]">
                <CheckCircle
                  aria-hidden
                  weight="fill"
                  className="size-4 text-[var(--brand-teal)]"
                />
                {t("library.title")}
                {meta && (
                  <span className="tabular-nums font-semibold text-[var(--text-muted)]">
                    ({meta.active_cv_used}/{meta.active_cv_limit})
                  </span>
                )}
              </h2>
              <p className="text-xs text-[var(--text-secondary)]">
                {t("library.subtitle")}
              </p>
            </div>

            {quotaStrip}

            {readyRows.length > 0 ? (
              <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {readyRows.map((cv) => (
                  <CvLibraryCard
                    key={cv.id}
                    cv={cv}
                    locale={locale}
                    busy={busyId === cv.id}
                    onOpen={() => goToBuilder(cv)}
                    onDuplicate={() => duplicate(cv)}
                    onDelete={() => setDeleteCandidate(cv)}
                  />
                ))}
              </ul>
            ) : (
              <div className="rounded-[14px] border border-dashed border-[var(--border-default)] bg-[var(--surface-card)] px-5 py-6 text-sm text-[var(--text-secondary)]">
                {t("library.emptyRow")}
              </div>
            )}
          </section>

          {/* ── Drafts: unlimited, not counted, not usable to apply/job-fit ── */}
          {draftRows.length > 0 && (
            <section className="mt-8">
              <div className="mb-2.5 flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
                <h2 className="flex items-center gap-1.5 text-sm font-bold text-[var(--text-primary)]">
                  <PencilLine
                    aria-hidden
                    weight="duotone"
                    className="size-4 text-[var(--text-muted)]"
                  />
                  {t("drafts.title")}
                  <span className="tabular-nums font-semibold text-[var(--text-muted)]">
                    ({draftRows.length})
                  </span>
                </h2>
                <p className="text-xs text-[var(--text-secondary)]">
                  {t("drafts.subtitle")}
                </p>
              </div>
              <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {draftRows.map((cv) => (
                  <CvLibraryCard
                    key={cv.id}
                    cv={cv}
                    locale={locale}
                    busy={busyId === cv.id}
                    onOpen={() => goToBuilder(cv)}
                    onDuplicate={() => duplicate(cv)}
                    onDelete={() => setDeleteCandidate(cv)}
                  />
                ))}
              </ul>
            </section>
          )}

          {query.hasNextPage && (
            <div className="mt-6 flex justify-center">
              <Button
                variant="secondary"
                loading={query.isFetchingNextPage}
                onClick={() => query.fetchNextPage()}
              >
                {tc("loadMore")}
              </Button>
            </div>
          )}
        </>
      )}

      <CvCreateModal
        open={createOpen}
        initialTemplateId={shelfTemplateId}
        onClose={() => {
          setCreateOpen(false);
          setShelfTemplateId(null);
        }}
        onCreated={(cv) => {
          setCreateOpen(false);
          setShelfTemplateId(null);
          refetchList();
          goToBuilder(cv);
        }}
        onOpenUpload={() => router.push("/student/cv/import")}
        onQuotaExceeded={(info) => setQuotaInfo(info)}
      />
      <CvQuotaModal
        open={quotaInfo !== null}
        info={quotaInfo}
        onClose={() => setQuotaInfo(null)}
        onGoToLibrary={goToLibrary}
      />
      <Modal
        open={deleteCandidate !== null}
        onClose={() => setDeleteCandidate(null)}
        title={t("list.deleteConfirmTitle")}
        description={
          deleteCandidate
            ? t("list.deleteConfirmBody", { title: deleteCandidate.title })
            : undefined
        }
        footer={
          <div className="flex justify-end gap-2">
            <Button
              variant="secondary"
              onClick={() => setDeleteCandidate(null)}
              disabled={busyId !== null}
            >
              {tc("cancel")}
            </Button>
            <Button
              variant="danger"
              loading={busyId !== null}
              onClick={() => deleteCandidate && void remove(deleteCandidate)}
            >
              {t("list.delete")}
            </Button>
          </div>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">
          {t("list.deleteConfirmNote")}
        </p>
      </Modal>
    </>
  );
}
