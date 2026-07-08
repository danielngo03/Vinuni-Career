"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  messagingApi,
  type RecipientDepartment,
  type RecipientOrg,
  type RecipientTarget,
  type RecipientUser,
} from "@/lib/api";
import { messagingRecipientsKey } from "./query-keys";

/** Debounce a fast-changing value (recipient search box). */
function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}

export interface GroupedRecipients {
  orgs: RecipientOrg[];
  departments: RecipientDepartment[];
  users: RecipientUser[];
}

function group(items: RecipientTarget[]): GroupedRecipients {
  const orgs: RecipientOrg[] = [];
  const departments: RecipientDepartment[] = [];
  const users: RecipientUser[] = [];
  for (const item of items) {
    if (item.kind === "org") orgs.push(item);
    else if (item.kind === "department") departments.push(item);
    else if (item.kind === "user") users.push(item);
  }
  return { orgs, departments, users };
}

/**
 * Debounced recipient search for the composer + assign pickers. The permission
 * matrix is enforced server-side (students receive `org` targets only), so the
 * grouped result is safe to render as-is. `enabled` lets callers suspend the
 * query while the modal is closed.
 */
export function useRecipientSearch(query: string, enabled = true) {
  const debounced = useDebounced(query.trim(), 250);
  const result = useQuery({
    queryKey: messagingRecipientsKey(debounced),
    queryFn: () => messagingApi.searchRecipients(debounced, 20),
    enabled,
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  });

  const grouped = useMemo(
    () => group(result.data ?? []),
    [result.data],
  );
  const total =
    grouped.orgs.length + grouped.departments.length + grouped.users.length;

  return {
    ...result,
    grouped,
    total,
    /** True once a debounced request has resolved with zero matches. */
    isEmpty: result.isSuccess && total === 0,
  };
}
