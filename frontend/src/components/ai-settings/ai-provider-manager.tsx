"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  Cloud,
  Key,
  Pencil,
  Plus,
  RotateCw,
  Settings2,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import {
  Button,
  Input,
  Modal,
  Select,
  Switch,
  Textarea,
  useToast,
} from "@/components/ui";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardToolbar,
  CardContent,
  StatusChip,
  DataTable,
  type ColumnDef,
  DetailSheet,
  DetailSheetSection,
  DetailRow,
  EmptyState,
} from "@/components/kit";
import {
  ApiError,
  aiAliasesApi,
  aiProvidersApi,
  AI_PROVIDER_TYPES,
  type AiAliasCreateBody,
  type AiAliasUpdateBody,
  type AiModelAliasRow,
  type AiProvider,
  type AiProviderCreateBody,
  type AiProviderType,
  type AiProviderUpdateBody,
} from "@/lib/api";

/* ------------------------------------------------------------------ helpers */

function KeyChip({ present }: { present: boolean }) {
  return (
    <StatusChip tone={present ? "success" : "neutral"} size="sm">
      <Key aria-hidden className="size-3" strokeWidth={2} />
      {present ? "Key set" : "No key"}
    </StatusChip>
  );
}

function BuiltinChip() {
  return (
    <StatusChip tone="violet" size="sm">
      Built-in
    </StatusChip>
  );
}

function ActiveChip({ active }: { active: boolean }) {
  return (
    <StatusChip tone={active ? "success" : "neutral"} size="sm" dot>
      {active ? "Active" : "Inactive"}
    </StatusChip>
  );
}

function providerTypeLabel(t: AiProviderType): string {
  return AI_PROVIDER_TYPES.find((p) => p.value === t)?.label ?? t;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/* ================================================================== PROVIDERS ================================================================== */

const EMPTY_PROVIDER: AiProviderCreateBody = {
  name: "",
  provider_type: "openai_compatible",
  base_url: "",
  description: "",
};

type ProviderFormMode = { mode: "create" } | { mode: "edit"; provider: AiProvider };

type ProviderFormState = {
  name: string;
  provider_type: AiProviderType;
  base_url: string;
  api_key: string;
  clear_api_key: boolean;
  description: string;
};

function ProviderForm({
  providers,
  mode,
  onClose,
  onSaved,
}: {
  providers: AiProvider[];
  mode: ProviderFormMode;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const isEdit = mode.mode === "edit";
  const initial: ProviderFormState = isEdit
    ? {
        name: mode.provider.name,
        provider_type: mode.provider.provider_type,
        base_url: mode.provider.base_url,
        api_key: "",
        clear_api_key: false,
        description: mode.provider.description ?? "",
      }
    : {
        name: EMPTY_PROVIDER.name,
        provider_type: EMPTY_PROVIDER.provider_type,
        base_url: EMPTY_PROVIDER.base_url,
        api_key: "",
        clear_api_key: false,
        description: EMPTY_PROVIDER.description ?? "",
      };

  const [form, setForm] = useState<ProviderFormState>(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});

  function patch(p: Partial<typeof initial>) {
    setForm((f) => ({ ...f, ...p }));
    if (p.name !== undefined) setErrors((e) => ({ ...e, name: "" }));
    if (p.base_url !== undefined) setErrors((e) => ({ ...e, base_url: "" }));
  }

  function validate(): boolean {
    const errs: Record<string, string> = {};
    if (!isEdit && !form.name.trim()) errs.name = "Provider name is required.";
    if (!isEdit) {
      const taken = providers.some(
        (p) => p.name.toLowerCase() === form.name.trim().toLowerCase(),
      );
      if (taken) errs.name = "A provider with this name already exists.";
    }
    if (form.provider_type !== "ollama" && !form.base_url.trim())
      errs.base_url = "Base URL is required for this provider type.";
    setErrors(errs);
    return Object.keys(errs).length === 0;
  }

  const createMut = useMutation({
    mutationFn: (body: AiProviderCreateBody) => aiProvidersApi.create(body),
    onSuccess: () => {
      toast.show({ tone: "success", title: "Provider added." });
      onSaved();
      onClose();
    },
    onError: (e) =>
      toast.show({
        tone: "error",
        title: e instanceof ApiError ? e.message : "Failed to add provider.",
      }),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: string; body: AiProviderUpdateBody }) =>
      aiProvidersApi.update(id, body),
    onSuccess: () => {
      toast.show({ tone: "success", title: "Provider updated." });
      onSaved();
      onClose();
    },
    onError: (e) =>
      toast.show({
        tone: "error",
        title: e instanceof ApiError ? e.message : "Failed to update provider.",
      }),
  });

  const pending = createMut.isPending || updateMut.isPending;

  function onSubmit() {
    if (!validate()) return;
    if (isEdit) {
      updateMut.mutate({
        id: mode.provider.id,
        body: {
          base_url: form.base_url.trim(),
          api_key: form.api_key.trim() || undefined,
          clear_api_key: form.clear_api_key || undefined,
          description: form.description.trim() || undefined,
          provider_type: form.provider_type,
        },
      });
    } else {
      createMut.mutate({
        name: form.name.trim().toLowerCase().replace(/\s+/g, "-"),
        provider_type: form.provider_type,
        base_url: form.base_url.trim(),
        api_key: form.api_key.trim() || undefined,
        description: form.description.trim() || undefined,
      });
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={isEdit ? "Edit provider" : "Add AI provider"}
      description={
        isEdit
          ? "Update endpoint metadata and rotate or clear the encrypted provider key."
          : "Register a provider endpoint and optionally store its encrypted API key."
      }
      size="md"
      closeLabel="Cancel"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button variant="primary" onClick={onSubmit} loading={pending}>
            {isEdit ? "Save changes" : "Add provider"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {!isEdit && (
          <Input
            id="prov-name"
            label="Provider name"
            placeholder="my-custom-provider"
            value={form.name}
            error={errors.name}
            help='Lowercase slug used as the env key suffix (AI_PROVIDER_{NAME}_API_KEY). Cannot be changed after creation.'
            onChange={(e) => patch({ name: e.target.value })}
          />
        )}
        <Select
          id="prov-type"
          label="Provider type"
          value={form.provider_type}
          onChange={(e) => patch({ provider_type: e.target.value as AiProviderType })}
          options={AI_PROVIDER_TYPES.map((t) => ({ value: t.value, label: t.label }))}
        />
        <Input
          id="prov-url"
          label="Base URL"
          placeholder="https://api.example.com/v1"
          value={form.base_url}
          error={errors.base_url}
          help="The root endpoint for this provider's OpenAI-compatible API."
          onChange={(e) => patch({ base_url: e.target.value })}
        />
        {form.provider_type !== "ollama" && (
          <div className="space-y-2">
            <Input
              id="prov-api-key"
              type="password"
              label={isEdit ? "API key (leave blank to keep current)" : "API key"}
              placeholder="sk-..."
              value={form.api_key}
              help="Stored encrypted at rest. The plaintext key is never returned by the API."
              onChange={(e) =>
                patch({ api_key: e.target.value, clear_api_key: false })
              }
            />
            {isEdit && mode.provider.has_api_key && (
              <label className="flex items-center justify-between gap-3 rounded-xl border border-border bg-[var(--bg-subtle)] px-3 py-2.5">
                <span className="min-w-0">
                  <span className="block text-sm font-medium text-[var(--text-primary)]">
                    Clear stored key
                  </span>
                  <span className="block text-xs text-[var(--text-muted)]">
                    Provider will fall back to environment variables if available.
                  </span>
                </span>
                <Switch
                  id="prov-clear-key"
                  checked={form.clear_api_key}
                  hideLabel
                  label="Clear stored key"
                  onCheckedChange={(v) =>
                    patch({ clear_api_key: v, api_key: v ? "" : form.api_key })
                  }
                />
              </label>
            )}
          </div>
        )}
        <Textarea
          id="prov-desc"
          label="Description"
          placeholder="Optional note about this provider…"
          value={form.description}
          rows={2}
          help="Internal note only — not shown to students or partners."
          onChange={(e) => patch({ description: e.target.value })}
        />
        {form.provider_type !== "ollama" && (
          <div className="flex items-start gap-2 rounded-xl border border-[var(--content-info)]/25 bg-[var(--content-info-soft)] px-3 py-2.5 text-sm text-[var(--content-info)]">
            <ShieldCheck aria-hidden className="mt-0.5 size-4 shrink-0" strokeWidth={2} />
            <p>
              Keys saved here are encrypted in the backend database. Environment
              variables can still be used as an operations fallback.
            </p>
          </div>
        )}
      </div>
    </Modal>
  );
}

/** Read-only registry detail for a provider (superadmin AI-ops surface). */
function ProviderDetailSheet({
  provider,
  onClose,
  onEdit,
}: {
  provider: AiProvider;
  onClose: () => void;
  onEdit: () => void;
}) {
  return (
    <DetailSheet
      open
      onClose={onClose}
      title={provider.name}
      subtitle={providerTypeLabel(provider.provider_type)}
      avatar={
        <span className="flex size-10 items-center justify-center rounded-xl bg-[var(--bg-muted)]">
          <Cloud aria-hidden className="size-5 text-[var(--text-muted)]" strokeWidth={1.8} />
        </span>
      }
      status={
        <>
          <ActiveChip active={provider.is_active} />
          {provider.is_builtin && <BuiltinChip />}
          <KeyChip present={provider.has_api_key} />
        </>
      }
      footer={
        <Button variant="secondary" onClick={onEdit}>
          <Pencil aria-hidden className="size-3.5" strokeWidth={2} />
          Edit provider
        </Button>
      }
    >
      <DetailSheetSection title="Endpoint">
        <DetailRow label="Provider type">{providerTypeLabel(provider.provider_type)}</DetailRow>
        <DetailRow label="Base URL">
          {provider.base_url ? (
            <span className="break-all font-mono text-xs">{provider.base_url}</span>
          ) : (
            "—"
          )}
        </DetailRow>
      </DetailSheetSection>
      <DetailSheetSection title="Credentials">
        <DetailRow label="API key">
          <KeyChip present={provider.has_api_key} />
        </DetailRow>
        <p className="mt-2 type-caption text-muted-foreground">
          The plaintext key is never returned by the API — it is stored encrypted
          at rest and only referenced by the gateway at call time.
        </p>
      </DetailSheetSection>
      {provider.description && (
        <DetailSheetSection title="Notes">
          <p className="text-sm text-foreground">{provider.description}</p>
        </DetailSheetSection>
      )}
      <DetailSheetSection title="Registry">
        <DetailRow label="Built-in">{provider.is_builtin ? "Yes" : "No"}</DetailRow>
        <DetailRow label="Status">{provider.is_active ? "Active" : "Inactive"}</DetailRow>
        <DetailRow label="Created">{fmtDate(provider.created_at)}</DetailRow>
        <DetailRow label="Updated">{fmtDate(provider.updated_at)}</DetailRow>
      </DetailSheetSection>
    </DetailSheet>
  );
}

export function ProvidersSection() {
  const qc = useQueryClient();
  const toast = useToast();
  const [formMode, setFormMode] = useState<ProviderFormMode | null>(null);
  const [detail, setDetail] = useState<AiProvider | null>(null);

  const query = useQuery({
    queryKey: ["admin", "ai-providers"],
    queryFn: () => aiProvidersApi.list(),
    retry: false,
  });

  const toggleMut = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      aiProvidersApi.update(id, { is_active }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["admin", "ai-providers"] }),
    onError: () => toast.show({ tone: "error", title: "Failed to update provider." }),
  });

  const providers = query.data ?? [];

  const columns: ColumnDef<AiProvider, unknown>[] = [
    {
      id: "provider",
      header: "Provider",
      enableSorting: false,
      cell: ({ row }) => {
        const p = row.original;
        return (
          <button
            type="button"
            onClick={() => setDetail(p)}
            className="group flex items-center gap-2.5 text-left outline-none"
          >
            <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-[var(--bg-muted)]">
              <Cloud aria-hidden className="size-4 text-[var(--text-muted)]" strokeWidth={1.8} />
            </span>
            <span className="min-w-0">
              <span className="flex items-center gap-1.5">
                <span className="truncate text-sm font-semibold text-foreground group-hover:text-[var(--brand-primary)]">
                  {p.name}
                </span>
                {p.is_builtin && <BuiltinChip />}
              </span>
              {p.description && (
                <span className="block max-w-[240px] truncate type-caption text-muted-foreground">
                  {p.description}
                </span>
              )}
            </span>
          </button>
        );
      },
    },
    {
      id: "type",
      header: "Type",
      enableSorting: false,
      cell: ({ row }) => (
        <span className="text-[0.8125rem] text-muted-foreground">
          {providerTypeLabel(row.original.provider_type)}
        </span>
      ),
    },
    {
      id: "endpoint",
      header: "Endpoint",
      enableSorting: false,
      cell: ({ row }) =>
        row.original.base_url ? (
          <span className="block max-w-[220px] truncate font-mono text-xs text-muted-foreground">
            {row.original.base_url}
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      id: "key",
      header: "Key",
      enableSorting: false,
      cell: ({ row }) => <KeyChip present={row.original.has_api_key} />,
    },
    {
      id: "actions",
      header: "Status",
      enableSorting: false,
      meta: { align: "right" },
      cell: ({ row }) => {
        const p = row.original;
        return (
          <div className="flex items-center justify-end gap-2">
            <Switch
              checked={p.is_active}
              onCheckedChange={(v) => toggleMut.mutate({ id: p.id, is_active: v })}
              label={p.is_active ? "Active" : "Inactive"}
              hideLabel
              id={`prov-toggle-${p.id}`}
            />
            <button
              type="button"
              onClick={() => setFormMode({ mode: "edit", provider: p })}
              className="flex size-7 items-center justify-center rounded-lg text-muted-foreground outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-foreground focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
              aria-label={`Edit ${p.name}`}
            >
              <Pencil aria-hidden className="size-3.5" strokeWidth={2} />
            </button>
          </div>
        );
      },
    },
  ];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2.5">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-lg icon-chip-info">
            <Cloud aria-hidden className="size-4" strokeWidth={2} />
          </span>
          <div>
            <CardTitle>AI Providers</CardTitle>
            <CardDescription>
              Registered endpoints with encrypted admin-managed keys
            </CardDescription>
          </div>
        </div>
        <CardToolbar>
          <Button variant="secondary" size="sm" onClick={() => setFormMode({ mode: "create" })}>
            <Plus aria-hidden className="size-4" strokeWidth={2} />
            Add provider
          </Button>
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {query.isError ? (
          <EmptyState
            kind="error"
            title="Couldn't load providers."
            description="Something went wrong fetching the provider registry."
            action={
              <Button variant="secondary" onClick={() => query.refetch()}>
                <RotateCw aria-hidden className="size-4" strokeWidth={2} />
                Retry
              </Button>
            }
          />
        ) : (
          <DataTable
            columns={columns}
            data={providers}
            getRowId={(p) => p.id}
            loading={query.isLoading}
            empty={
              <EmptyState
                kind="empty"
                title="No providers configured yet."
                description="Add a provider endpoint to route AI aliases to concrete models."
              />
            }
          />
        )}
      </CardContent>

      {formMode && (
        <ProviderForm
          providers={providers}
          mode={formMode}
          onClose={() => setFormMode(null)}
          onSaved={() => void qc.invalidateQueries({ queryKey: ["admin", "ai-providers"] })}
        />
      )}
      {detail && (
        <ProviderDetailSheet
          provider={detail}
          onClose={() => setDetail(null)}
          onEdit={() => {
            setFormMode({ mode: "edit", provider: detail });
            setDetail(null);
          }}
        />
      )}
    </Card>
  );
}

/* ================================================================== ALIASES ================================================================== */

const EMPTY_ALIAS: AiAliasCreateBody = {
  alias_name: "",
  model_id: "",
  provider_id: "",
  task_families: "",
  description: "",
};

type AliasFormState = {
  alias_name: string;
  model_id: string;
  provider_id: string;
  task_families: string;
  description: string;
};

type AliasFormMode =
  | { mode: "create" }
  | { mode: "edit"; alias: AiModelAliasRow };

function AliasForm({
  providers,
  aliases,
  mode,
  onClose,
  onSaved,
}: {
  providers: AiProvider[];
  aliases: AiModelAliasRow[];
  mode: AliasFormMode;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const isEdit = mode.mode === "edit";
  const initial: AliasFormState = isEdit
    ? {
        alias_name: mode.alias.alias_name,
        model_id: "",
        provider_id: mode.alias.provider_id,
        task_families: mode.alias.task_families ?? "",
        description: mode.alias.description ?? "",
      }
    : {
        alias_name: EMPTY_ALIAS.alias_name,
        model_id: EMPTY_ALIAS.model_id,
        provider_id: EMPTY_ALIAS.provider_id,
        task_families: EMPTY_ALIAS.task_families ?? "",
        description: EMPTY_ALIAS.description ?? "",
      };

  const [form, setForm] = useState<AliasFormState>(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});

  function patch(p: Partial<AliasFormState>) {
    setForm((f) => ({ ...f, ...p }));
    const cleared: Record<string, string> = {};
    for (const k of Object.keys(p)) cleared[k] = "";
    setErrors((e) => ({ ...e, ...cleared }));
  }

  function validate(): boolean {
    const errs: Record<string, string> = {};
    if (!isEdit && !form.alias_name.trim()) errs.alias_name = "Alias name is required.";
    if (!isEdit) {
      const taken = aliases.some(
        (a) => a.alias_name.toLowerCase() === form.alias_name.trim().toLowerCase(),
      );
      if (taken) errs.alias_name = "An alias with this name already exists.";
    }
    if (!form.provider_id) errs.provider_id = "Select a provider.";
    if (!isEdit && !form.model_id.trim())
      errs.model_id = "Model ID is required (e.g. openai/gpt-4o).";
    if (isEdit && form.model_id.trim() === "" && !mode.alias.alias_name) {
      /* allow empty model_id on edit when user doesn't want to change it */
    }
    setErrors(errs);
    return Object.keys(errs).length === 0;
  }

  const createMut = useMutation({
    mutationFn: (body: AiAliasCreateBody) => aiAliasesApi.create(body),
    onSuccess: () => {
      toast.show({ tone: "success", title: "Alias created." });
      onSaved();
      onClose();
    },
    onError: (e) =>
      toast.show({
        tone: "error",
        title: e instanceof ApiError ? e.message : "Failed to create alias.",
      }),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: string; body: AiAliasUpdateBody }) =>
      aiAliasesApi.update(id, body),
    onSuccess: () => {
      toast.show({ tone: "success", title: "Alias updated." });
      onSaved();
      onClose();
    },
    onError: (e) =>
      toast.show({
        tone: "error",
        title: e instanceof ApiError ? e.message : "Failed to update alias.",
      }),
  });

  const pending = createMut.isPending || updateMut.isPending;
  const activeProviders = providers.filter((p) => p.is_active);

  function onSubmit() {
    if (!validate()) return;
    if (isEdit) {
      const body: AiAliasUpdateBody = {
        provider_id: form.provider_id,
        task_families: form.task_families.trim() || undefined,
        description: form.description.trim() || undefined,
      };
      if (form.model_id.trim()) body.model_id = form.model_id.trim();
      updateMut.mutate({ id: mode.alias.id, body });
    } else {
      createMut.mutate({
        alias_name: form.alias_name.trim().toLowerCase().replace(/\s+/g, "_"),
        model_id: form.model_id.trim(),
        provider_id: form.provider_id,
        task_families: form.task_families.trim() || undefined,
        description: form.description.trim() || undefined,
      });
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={isEdit ? `Edit alias "${mode.alias.alias_name}"` : "Create model alias"}
      description={
        isEdit
          ? "Update routing for this alias. The model ID routes this alias to a specific model at the provider — it is never surfaced to end users."
          : "Create a logical alias that maps to a concrete model at a provider. The model ID is stored securely and never shown to users."
      }
      size="md"
      closeLabel="Cancel"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button variant="primary" onClick={onSubmit} loading={pending}>
            {isEdit ? "Save changes" : "Create alias"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {!isEdit && (
          <Input
            id="alias-name"
            label="Alias name"
            placeholder="chat_fast"
            value={form.alias_name}
            error={errors.alias_name}
            help="Logical name used in code and AI settings (e.g. chat_cheap, reasoning_best). Snake_case."
            onChange={(e) => patch({ alias_name: e.target.value })}
          />
        )}
        <Select
          id="alias-provider"
          label="Provider"
          value={form.provider_id}
          error={errors.provider_id}
          onChange={(e) => patch({ provider_id: e.target.value })}
          options={[
            { value: "", label: "— Select provider —" },
            ...activeProviders.map((p) => ({ value: p.id, label: p.name })),
          ]}
        />
        <Input
          id="alias-model-id"
          label={isEdit ? "Model ID (leave blank to keep current)" : "Model ID"}
          placeholder="openai/gpt-4o-mini"
          value={form.model_id}
          error={errors.model_id}
          help="Exact model identifier sent to the provider API. Never shown to students or partners."
          onChange={(e) => patch({ model_id: e.target.value })}
        />
        <Input
          id="alias-families"
          label="Task families (optional)"
          placeholder="chat,rerank,eval"
          value={form.task_families}
          help="Comma-separated: chat, reasoning, embedding, rerank, eval. Leave blank for any family."
          onChange={(e) => patch({ task_families: e.target.value })}
        />
        <Textarea
          id="alias-desc"
          label="Description (optional)"
          placeholder="Fast 8B model for low-cost chat completions…"
          value={form.description}
          rows={2}
          onChange={(e) => patch({ description: e.target.value })}
        />
        <div className="flex items-start gap-2 rounded-xl border border-[var(--content-info)]/25 bg-[var(--content-info-soft)] px-3 py-2.5 text-sm text-[var(--content-info)]">
          <ShieldAlert aria-hidden className="mt-0.5 size-4 shrink-0" strokeWidth={2} />
          <p>
            Model IDs are stored securely and never returned in API responses or
            shown to non-admin users. Alias names (e.g.{" "}
            <code className="rounded bg-[var(--bg-muted)] px-1 font-mono text-xs">chat_cheap</code>)
            are the only identifiers surfaced to students and partners.
          </p>
        </div>
      </div>
    </Modal>
  );
}

/** Read-only registry detail for a model alias (superadmin AI-ops surface). */
function AliasDetailSheet({
  alias,
  onClose,
  onEdit,
}: {
  alias: AiModelAliasRow;
  onClose: () => void;
  onEdit: () => void;
}) {
  return (
    <DetailSheet
      open
      onClose={onClose}
      title={alias.alias_name}
      subtitle={alias.provider_name ?? "Unassigned provider"}
      avatar={
        <span className="flex size-10 items-center justify-center rounded-xl bg-[var(--ai-accent-soft)]">
          <Bot aria-hidden className="size-5 text-[var(--ai-accent)]" strokeWidth={1.8} />
        </span>
      }
      status={
        <>
          <ActiveChip active={alias.is_active} />
          {alias.is_builtin && <BuiltinChip />}
        </>
      }
      footer={
        <Button variant="secondary" onClick={onEdit}>
          <Pencil aria-hidden className="size-3.5" strokeWidth={2} />
          Edit alias
        </Button>
      }
    >
      <DetailSheetSection title="Routing">
        <DetailRow label="Alias name">
          <code className="rounded bg-[var(--bg-muted)] px-1.5 py-0.5 font-mono text-xs font-semibold text-foreground">
            {alias.alias_name}
          </code>
        </DetailRow>
        <DetailRow label="Provider">{alias.provider_name ?? "—"}</DetailRow>
        <DetailRow label="Task families">{alias.task_families || "Any"}</DetailRow>
      </DetailSheetSection>
      {alias.description && (
        <DetailSheetSection title="Notes">
          <p className="text-sm text-foreground">{alias.description}</p>
        </DetailSheetSection>
      )}
      <DetailSheetSection title="Registry">
        <DetailRow label="Built-in">{alias.is_builtin ? "Yes" : "No"}</DetailRow>
        <DetailRow label="Status">{alias.is_active ? "Active" : "Inactive"}</DetailRow>
        <DetailRow label="Created">{fmtDate(alias.created_at)}</DetailRow>
        <DetailRow label="Updated">{fmtDate(alias.updated_at)}</DetailRow>
      </DetailSheetSection>
      <div className="px-5 py-4">
        <p className="flex items-start gap-2 type-caption text-muted-foreground">
          <ShieldAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" strokeWidth={2} />
          The concrete model ID this alias routes to is stored write-only and is
          never returned by the API. Edit the alias to re-point its routing.
        </p>
      </div>
    </DetailSheet>
  );
}

export function AliasesSection({ providers }: { providers: AiProvider[] }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [formMode, setFormMode] = useState<AliasFormMode | null>(null);
  const [detail, setDetail] = useState<AiModelAliasRow | null>(null);

  const query = useQuery({
    queryKey: ["admin", "ai-aliases"],
    queryFn: () => aiAliasesApi.list(),
    retry: false,
  });

  const toggleMut = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      aiAliasesApi.update(id, { is_active }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["admin", "ai-aliases"] }),
    onError: () => toast.show({ tone: "error", title: "Failed to update alias." }),
  });

  const aliases = query.data ?? [];

  const columns: ColumnDef<AiModelAliasRow, unknown>[] = [
    {
      id: "alias",
      header: "Alias",
      enableSorting: false,
      cell: ({ row }) => {
        const a = row.original;
        return (
          <button
            type="button"
            onClick={() => setDetail(a)}
            className="group flex items-center gap-2.5 text-left outline-none"
          >
            <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-[var(--ai-accent-soft)]">
              <Bot aria-hidden className="size-4 text-[var(--ai-accent)]" strokeWidth={1.8} />
            </span>
            <span className="min-w-0">
              <span className="flex items-center gap-1.5">
                <code className="rounded bg-[var(--bg-subtle)] px-1.5 py-0.5 font-mono text-xs font-semibold text-foreground group-hover:text-[var(--brand-primary)]">
                  {a.alias_name}
                </code>
                {a.is_builtin && <BuiltinChip />}
              </span>
              {a.description && (
                <span className="block max-w-[240px] truncate type-caption text-muted-foreground">
                  {a.description}
                </span>
              )}
            </span>
          </button>
        );
      },
    },
    {
      id: "provider",
      header: "Provider",
      enableSorting: false,
      cell: ({ row }) => (
        <span className="text-[0.8125rem] text-muted-foreground">
          {row.original.provider_name ?? "—"}
        </span>
      ),
    },
    {
      id: "families",
      header: "Task families",
      enableSorting: false,
      cell: ({ row }) =>
        row.original.task_families ? (
          <span className="font-mono text-xs text-muted-foreground">
            {row.original.task_families}
          </span>
        ) : (
          <span className="text-muted-foreground">Any</span>
        ),
    },
    {
      id: "actions",
      header: "Status",
      enableSorting: false,
      meta: { align: "right" },
      cell: ({ row }) => {
        const a = row.original;
        return (
          <div className="flex items-center justify-end gap-2">
            <Switch
              checked={a.is_active}
              onCheckedChange={(v) => toggleMut.mutate({ id: a.id, is_active: v })}
              label={a.is_active ? "Active" : "Inactive"}
              hideLabel
              id={`alias-toggle-${a.id}`}
            />
            <button
              type="button"
              onClick={() => setFormMode({ mode: "edit", alias: a })}
              className="flex size-7 items-center justify-center rounded-lg text-muted-foreground outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-foreground focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
              aria-label={`Edit alias ${a.alias_name}`}
            >
              <Pencil aria-hidden className="size-3.5" strokeWidth={2} />
            </button>
          </div>
        );
      },
    },
  ];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2.5">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-lg icon-chip-info">
            <Bot aria-hidden className="size-4" strokeWidth={2} />
          </span>
          <div>
            <CardTitle>Model Aliases</CardTitle>
            <CardDescription>
              Logical names that route to concrete models at registered providers
            </CardDescription>
          </div>
        </div>
        <CardToolbar>
          <Button variant="secondary" size="sm" onClick={() => setFormMode({ mode: "create" })}>
            <Plus aria-hidden className="size-4" strokeWidth={2} />
            Add alias
          </Button>
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {query.isError ? (
          <EmptyState
            kind="error"
            title="Couldn't load aliases."
            description="Something went wrong fetching the model alias registry."
            action={
              <Button variant="secondary" onClick={() => query.refetch()}>
                <RotateCw aria-hidden className="size-4" strokeWidth={2} />
                Retry
              </Button>
            }
          />
        ) : (
          <DataTable
            columns={columns}
            data={aliases}
            getRowId={(a) => a.id}
            loading={query.isLoading}
            empty={
              <EmptyState
                kind="empty"
                title="No aliases configured yet."
                description="Create a logical alias to route AI tasks to a concrete model."
              />
            }
          />
        )}
      </CardContent>

      {formMode && (
        <AliasForm
          providers={providers}
          aliases={aliases}
          mode={formMode}
          onClose={() => setFormMode(null)}
          onSaved={() => void qc.invalidateQueries({ queryKey: ["admin", "ai-aliases"] })}
        />
      )}
      {detail && (
        <AliasDetailSheet
          alias={detail}
          onClose={() => setDetail(null)}
          onEdit={() => {
            setFormMode({ mode: "edit", alias: detail });
            setDetail(null);
          }}
        />
      )}
    </Card>
  );
}

/* ================================================================== COMBINED PANEL ================================================================== */

export function AiProviderManager() {
  const providersQuery = useQuery({
    queryKey: ["admin", "ai-providers"],
    queryFn: () => aiProvidersApi.list(),
    retry: false,
  });

  const providers = providersQuery.data ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 px-1">
        <Settings2 aria-hidden className="size-4 text-muted-foreground" strokeWidth={1.8} />
        <span className="type-small font-semibold text-[var(--text-secondary)]">
          Multi-provider configuration
        </span>
        <span className="ml-auto flex items-center gap-1 type-caption text-muted-foreground">
          <ShieldAlert aria-hidden className="size-3.5" strokeWidth={1.8} />
          Model IDs are never exposed to students or partners
        </span>
      </div>
      <ProvidersSection />
      <AliasesSection providers={providers} />
    </div>
  );
}
