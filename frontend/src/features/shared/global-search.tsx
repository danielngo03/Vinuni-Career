"use client";

import {
  ArrowRight,
  Briefcase,
  FileText,
  MagnifyingGlass,
  SpinnerGap,
} from "@phosphor-icons/react";
import { useState } from "react";
import { toast } from "sonner";
import { apiFetch, apiMessage } from "@/lib/api/client";
import type { SearchResponse } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/provider";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";

export function GlobalSearch({
  open,
  onOpenChange,
  initialQuery = "",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialQuery?: string;
}) {
  const { dictionary } = useI18n();
  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<SearchResponse["results"]>([]);
  const [loading, setLoading] = useState(false);

  async function search(event: React.FormEvent) {
    event.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    try {
      const response = await apiFetch<SearchResponse>("/search", {
        method: "POST",
        body: JSON.stringify({ query: query.trim(), limit: 20 }),
      });
      setResults(response.results);
    } catch (error) {
      toast.error(apiMessage(error, dictionary.common.retry));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={dictionary.shell.globalSearch}
      description={dictionary.shell.searchHint}
    >
      <form onSubmit={search}>
        <div className="relative">
          <MagnifyingGlass className="absolute left-4 top-1/2 size-5 -translate-y-1/2 text-muted" />
          <Input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={dictionary.common.search}
            className="h-12 rounded-xl bg-slate-50 pl-12 pr-12"
          />
          {loading ? (
            <SpinnerGap className="absolute right-4 top-1/2 size-5 -translate-y-1/2 animate-spin text-primary" />
          ) : null}
        </div>
      </form>
      <div className="mt-5 max-h-[55vh] overflow-y-auto">
        {!results.length && !loading ? (
          <EmptyState
            icon={MagnifyingGlass}
            title={dictionary.common.empty}
            description={dictionary.shell.searchHint}
          />
        ) : (
          <div className="space-y-2">
            {results.map((result) => {
              const Icon = result.entity_type === "job" ? Briefcase : FileText;
              return (
                <button
                  key={`${result.entity_type}-${result.id}`}
                  type="button"
                  className="focus-ring flex w-full cursor-pointer items-center gap-3 rounded-xl border p-3 text-left hover:border-blue-200 hover:bg-blue-50/40"
                >
                  <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-primary">
                    <Icon className="size-5" weight="duotone" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold">{result.title}</p>
                    <div className="mt-1 flex items-center gap-2">
                      <Badge tone="blue">{result.entity_type}</Badge>
                      <span className="text-xs text-muted">
                        {Math.round(result.score)}%
                      </span>
                    </div>
                  </div>
                  <ArrowRight className="size-4 text-muted" />
                </button>
              );
            })}
          </div>
        )}
      </div>
    </Modal>
  );
}
