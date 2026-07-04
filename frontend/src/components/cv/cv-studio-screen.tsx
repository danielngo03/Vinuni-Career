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
  FilePlus,
  FileText,
  SignIn,
  UploadSimple,
  WarningCircle,
} from "@phosphor-icons/react";
import { useRouter } from "@/i18n/navigation";
import { Button, EmptyState, Skeleton, useToast } from "@/components/ui";
import { CvCreateModal } from "./cv-create-modal";
import { CvQuotaModal } from "./cv-quota-modal";
import { CvStudioHeader } from "./studio/cv-studio-header";
import { TemplateShelf } from "./studio/template-shelf";
import { QuotaStrip } from "./studio/quota-strip";
import { LibraryInsights } from "./studio/library-insights";
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

  // Quota meta is identical across pages; read it from the first fetched page.
  const meta = query.data?.pages[0]?.meta ?? null;
  const canCreate = meta?.can_create ?? true;
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

  async function archive(cv: CvSummary) {
    setBusyId(cv.id);
    try {
      await cvApi.update(cv.id, {
        status: "archived",
        expected_version: cv.version,
      });
      toast.show({ tone: "success", title: t("list.archivedToast") });
      refetchList();
    } catch (e) {
      if (e instanceof ApiError && e.isConflict) {
        toast.show({ tone: "warning", title: tc("conflictReload") });
        refetchList();
      } else {
        toast.show({ tone: "error", title: apiError(e) });
      }
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

  async function setPrimary(cv: CvSummary) {
    setBusyId(cv.id);
    try {
      await cvApi.update(cv.id, {
        is_primary: true,
        expected_version: cv.version,
      });
      toast.show({ tone: "success", title: t("list.primarySetToast") });
      refetchList();
    } catch (e) {
      if (e instanceof ApiError && e.code === "CONFLICT") {
        toast.show({ tone: "warning", title: tc("conflictReload") });
        refetchList();
      } else {
        toast.show({ tone: "error", title: apiError(e) });
      }
    } finally {
      setBusyId(null);
    }
  }

  const headerActions = (
    <>
      <Button
        variant="secondary"
        onClick={() => router.push("/student/cv/import")}
        disabled={!canCreate}
        title={!canCreate ? limitHint : undefined}
      >
        <UploadSimple aria-hidden weight="bold" className="size-4" />
        {t("list.upload")}
      </Button>
      <Button
        variant="primary"
        onClick={() => setCreateOpen(true)}
        disabled={!canCreate}
        title={!canCreate ? limitHint : undefined}
      >
        <FilePlus aria-hidden weight="bold" className="size-4" />
        {t("list.newCv")}
      </Button>
    </>
  );

  const quotaStrip = <QuotaStrip meta={meta} />;

  const templateShelf = (
    <TemplateShelf
      templates={templates.data ?? []}
      canCreate={canCreate}
      limitHint={limitHint}
      onSelect={startFromTemplate}
    />
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
          {quotaStrip}

          {/* CV Library Guidance — deterministic product rules, not AI. */}
          <LibraryInsights rows={rows} meta={meta} />

          <h2 className="mb-2.5 text-sm font-bold text-[var(--text-primary)]">
            {t("list.libraryTitle")}
          </h2>
          <ul
            id="cv-library"
            className="grid scroll-mt-24 gap-3 sm:grid-cols-2 xl:grid-cols-3"
          >
            {rows.map((cv) => (
              <CvLibraryCard
                key={cv.id}
                cv={cv}
                locale={locale}
                canCreate={canCreate}
                limitHint={limitHint}
                busy={busyId === cv.id}
                onOpen={() => goToBuilder(cv)}
                onDuplicate={() => duplicate(cv)}
                onSetPrimary={() => setPrimary(cv)}
                onArchive={() => archive(cv)}
              />
            ))}
          </ul>

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
    </>
  );
}
