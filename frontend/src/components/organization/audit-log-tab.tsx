"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Button, EmptyState, Input } from "@/components/ui";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  DataTable,
  type ColumnDef,
} from "@/components/kit";
import { ApiError, organizationApi, type AuditLogEntry } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

/** Human-readable rendering of a dotted audit action code, e.g.
 * "membership.deactivated" -> "membership deactivated". Never shows raw enum
 * codes verbatim per CLAUDE.md. */
function humanizeAction(action: string): string {
  return action.replaceAll(".", " ").replaceAll("_", " ");
}

export function AuditLogTab() {
  const t = useTranslations("team.auditLog");
  const tc = useTranslations("common");
  const locale = useLocale();

  const [actionFilter, setActionFilter] = React.useState("");
  const [actorFilter, setActorFilter] = React.useState("");
  const [appliedAction, setAppliedAction] = React.useState("");
  const [appliedActor, setAppliedActor] = React.useState("");

  const query = useInfiniteQuery({
    queryKey: ["org", "audit-log", appliedAction, appliedActor],
    queryFn: ({ pageParam }) => organizationApi.listAuditLog({ cursor: pageParam, action: appliedAction || undefined }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.page.next_cursor ?? undefined,
    retry: false,
  });

  const permissionDenied =
    query.isError && query.error instanceof ApiError && query.error.isPermissionError;

  const rows = (query.data?.pages.flatMap((p) => p.data) ?? []).filter((row) =>
    appliedActor ? (row.actor_email ?? "").toLowerCase().includes(appliedActor.toLowerCase()) : true,
  );

  const columns: ColumnDef<AuditLogEntry, unknown>[] = [
    {
      accessorKey: "actor_email",
      header: t("actor"),
      cell: ({ row }) => <span className="text-foreground">{row.original.actor_email ?? t("systemActor")}</span>,
    },
    {
      accessorKey: "action",
      header: t("action"),
      cell: ({ row }) => <span className="font-medium text-foreground">{humanizeAction(row.original.action)}</span>,
    },
    {
      accessorKey: "resource_type",
      header: t("resource"),
      enableSorting: false,
      cell: ({ row }) => <span className="text-muted-foreground">{row.original.resource_type ?? "—"}</span>,
    },
    {
      accessorKey: "occurred_at",
      header: t("time"),
      meta: { align: "right" },
      cell: ({ row }) => (
        <span className="whitespace-nowrap tabular-nums text-muted-foreground">
          {row.original.occurred_at ? formatDateTime(row.original.occurred_at, locale) : "—"}
        </span>
      ),
    },
  ];

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("title")}</CardTitle>
          <CardDescription>{t("intro")}</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        {permissionDenied ? (
          <EmptyState kind="permission" title={t("permissionTitle")} description={t("permissionBody")} />
        ) : (
          <>
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
              data={rows}
              getRowId={(row) => String(row.id)}
              loading={query.isPending}
              empty={<EmptyState kind="empty" title={t("empty")} />}
            />
            {query.hasNextPage && (
              <div className="mt-4 flex justify-center">
                <Button variant="secondary" loading={query.isFetchingNextPage} onClick={() => query.fetchNextPage()}>
                  {tc("loadMore")}
                </Button>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
