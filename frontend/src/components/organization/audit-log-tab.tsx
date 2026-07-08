"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useInfiniteQuery } from "@tanstack/react-query";
import { ClockCounterClockwise, ShieldWarning } from "@phosphor-icons/react";
import { Button, DataTable, EmptyState, Input, type Column } from "@/components/ui";
import { SectionCard } from "@/components/settings/section-card";
import { ApiError, organizationApi, type AuditLogEntry } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useOrgScope, orgScopedKey } from "./org-scope";

/** Human-readable rendering of a dotted audit action code, e.g.
 * "membership.deactivated" -> "membership deactivated". Never shows raw enum
 * codes verbatim per CLAUDE.md; this is a best-effort humanizer for an
 * open-ended action vocabulary that spans every module's write paths. */
function humanizeAction(action: string): string {
  return action.replaceAll(".", " ").replaceAll("_", " ");
}

export function AuditLogTab() {
  const t = useTranslations("team.auditLog");
  const tc = useTranslations("common");
  const locale = useLocale();
  const { orgId } = useOrgScope();

  const [actionFilter, setActionFilter] = useState("");
  const [actorFilter, setActorFilter] = useState("");
  const [appliedAction, setAppliedAction] = useState("");
  const [appliedActor, setAppliedActor] = useState("");

  const query = useInfiniteQuery({
    queryKey: orgScopedKey(["org", "audit-log", appliedAction, appliedActor], orgId),
    queryFn: ({ pageParam }) =>
      organizationApi.listAuditLog(
        {
          cursor: pageParam,
          action: appliedAction || undefined,
        },
        orgId,
      ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.page.next_cursor ?? undefined,
    retry: false,
  });

  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError) {
      return (
        <SectionCard
          title={t("title")}
          description={t("intro")}
          icon={ClockCounterClockwise}
          iconGradient="icon-chip-neutral"
        >
          <EmptyState
            kind="permission"
            icon={ShieldWarning}
            title={t("permissionTitle")}
            description={t("permissionBody")}
          />
        </SectionCard>
      );
    }
  }

  const rows = (query.data?.pages.flatMap((p) => p.data) ?? []).filter((row) =>
    appliedActor
      ? (row.actor_email ?? "").toLowerCase().includes(appliedActor.toLowerCase())
      : true,
  );

  const columns: Column<AuditLogEntry>[] = [
    {
      key: "actor",
      header: t("actor"),
      cell: (row) => row.actor_email ?? t("systemActor"),
    },
    {
      key: "action",
      header: t("action"),
      cell: (row) => (
        <span className="font-mono text-xs text-[var(--text-primary)]">
          {humanizeAction(row.action)}
        </span>
      ),
    },
    {
      key: "resource",
      header: t("resource"),
      cell: (row) => row.resource_type ?? "—",
    },
    {
      key: "time",
      header: t("time"),
      cell: (row) => (row.occurred_at ? formatDateTime(row.occurred_at, locale) : "—"),
    },
  ];

  return (
    <SectionCard title={t("title")} description={t("intro")}>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <Input
          label={t("filterAction")}
          placeholder={t("filterActionPlaceholder")}
          value={actionFilter}
          onChange={(e) => setActionFilter(e.target.value)}
          className="max-w-[220px]"
        />
        <Input
          label={t("filterActor")}
          value={actorFilter}
          onChange={(e) => setActorFilter(e.target.value)}
          className="max-w-[220px]"
        />
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            setAppliedAction(actionFilter.trim());
            setAppliedActor(actorFilter.trim());
          }}
        >
          {t("apply")}
        </Button>
        {(appliedAction || appliedActor) && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setActionFilter("");
              setActorFilter("");
              setAppliedAction("");
              setAppliedActor("");
            }}
          >
            {t("clearFilters")}
          </Button>
        )}
      </div>

      <DataTable
        columns={columns}
        rows={rows}
        getRowId={(row) => String(row.id)}
        loading={query.isPending}
        caption={t("title")}
        empty={{ kind: "empty", icon: ClockCounterClockwise, title: t("empty") }}
      />
      {query.hasNextPage && (
        <div className="mt-4 flex justify-center">
          <Button
            variant="secondary"
            loading={query.isFetchingNextPage}
            onClick={() => query.fetchNextPage()}
          >
            {tc("loadMore")}
          </Button>
        </div>
      )}
    </SectionCard>
  );
}
