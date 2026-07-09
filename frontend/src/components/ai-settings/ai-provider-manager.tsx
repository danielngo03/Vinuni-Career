"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowsClockwise,
  Cloud,
  Code,
  Database,
  GearSix,
  Key,
  Link,
  PencilSimple,
  Plus,
  Robot,
  ShieldWarning,
  Tag,
  Warning,
  XCircle,
} from "@phosphor-icons/react";
import {
  Button,
  Input,
  Modal,
  Select,
  StatusBadge,
  Switch,
  Textarea,
  useToast,
} from "@/components/ui";
import { cn } from "@/lib/utils";
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

function KeyBadge({ present }: { present: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold",
        present
          ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
          : "bg-slate-50 text-slate-500 border border-slate-200",
      )}
    >
      <Key aria-hidden weight="bold" className="size-3" />
      {present ? "Key set" : "No key"}
    </span>
  );
}

function BuiltinBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-violet-50 px-2 py-0.5 text-xs font-semibold text-violet-700 border border-violet-200">
      <Database aria-hidden weight="bold" className="size-3" />
      Built-in
    </span>
  );
}

function providerTypeLabel(t: AiProviderType): string {
  return AI_PROVIDER_TYPES.find((p) => p.value === t)?.label ?? t;
}

/* ------------------------------------------------------------------ section wrapper */

function SectionCard({
  title,
  subtitle,
  icon: IconCmp,
  iconGradient,
  action,
  children,
}: {
  title: string;
  subtitle?: string;
  icon: typeof Cloud;
  iconGradient: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-white/60 bg-white/82 shadow-[0_2px_12px_rgba(11,34,57,0.06)] backdrop-blur-md overflow-hidden">
      <div className="flex items-start justify-between gap-3 px-5 py-4 border-b border-[var(--border-subtle)]">
        <div className="flex items-center gap-2.5 min-w-0">
          <span
            className={cn(
              "flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm",
              iconGradient,
            )}
          >
            <IconCmp aria-hidden weight="duotone" className="size-4 text-white" />
          </span>
          <div className="min-w-0">
            <h2 className="text-base font-bold text-[var(--text-primary)]">{title}</h2>
            {subtitle && (
              <p className="mt-0.5 text-xs text-[var(--text-secondary)]">{subtitle}</p>
            )}
          </div>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
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
        // base_url is write-only (never returned by the API), so edit starts
        // blank; leaving it blank keeps the current endpoint on save.
        base_url: "",
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
    // On CREATE a base URL is required; on EDIT it is write-only and optional
    // (blank keeps the current endpoint, which the API never returns).
    if (!isEdit && form.provider_type !== "ollama" && !form.base_url.trim())
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
          // Omit when blank so the existing (write-only) endpoint is kept.
          base_url: form.base_url.trim() || undefined,
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
          label={isEdit ? "Base URL (leave blank to keep current)" : "Base URL"}
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
              <label className="flex items-center justify-between gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-3 py-2.5">
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
          <div className="flex items-start gap-2 rounded-xl bg-emerald-50 px-3 py-2.5 text-sm text-emerald-800 border border-emerald-200">
            <Warning aria-hidden weight="fill" className="size-4 shrink-0 mt-0.5" />
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

export function ProvidersSection() {
  const qc = useQueryClient();
  const toast = useToast();
  const [formMode, setFormMode] = useState<ProviderFormMode | null>(null);

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

  return (
    <SectionCard
      title="AI Providers"
      subtitle="Registered endpoints with encrypted admin-managed keys"
      icon={Cloud}
      iconGradient="icon-chip-info"
      action={
        <Button
          variant="secondary"
          onClick={() => setFormMode({ mode: "create" })}
          className="shrink-0"
        >
          <Plus aria-hidden weight="bold" className="size-4" />
          Add provider
        </Button>
      }
    >
      {query.isLoading && (
        <div className="divide-y divide-[var(--border-subtle)]">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-14 animate-pulse bg-[var(--bg-subtle)]" />
          ))}
        </div>
      )}
      {query.isError && (
        <div className="flex items-center gap-2 px-5 py-4 text-sm text-[var(--brand-red)]">
          <XCircle aria-hidden weight="fill" className="size-4 shrink-0" />
          Failed to load providers.
          <Button variant="ghost" onClick={() => query.refetch()} className="ml-auto">
            <ArrowsClockwise aria-hidden className="size-4" /> Retry
          </Button>
        </div>
      )}
      {!query.isLoading && !query.isError && providers.length === 0 && (
        <p className="px-5 py-6 text-center text-sm text-[var(--text-muted)]">
          No providers configured yet.
        </p>
      )}
      {providers.length > 0 && (
        <div className="divide-y divide-[var(--border-subtle)]">
          {providers.map((p) => (
            <div
              key={p.id}
              className={cn(
                "flex items-center gap-3 px-5 py-3.5",
                !p.is_active && "opacity-50",
              )}
            >
              {/* Icon */}
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-slate-100 to-slate-200 shadow-sm">
                <Cloud aria-hidden weight="duotone" className="size-4 text-slate-500" />
              </span>
              {/* Name + badges */}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-sm font-semibold text-[var(--text-primary)]">
                    {p.name}
                  </span>
                  {p.is_builtin && <BuiltinBadge />}
                  <KeyBadge present={p.has_api_key} />
                </div>
                <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-[var(--text-muted)]">
                  <span className="inline-flex items-center gap-1">
                    <Code aria-hidden className="size-3" />
                    {providerTypeLabel(p.provider_type)}
                  </span>
                  {p.has_base_url && (
                    <span className="inline-flex items-center gap-1">
                      <Link aria-hidden className="size-3 shrink-0" />
                      Endpoint set
                    </span>
                  )}
                  {p.description && (
                    <span className="hidden sm:inline text-[var(--text-muted)]">
                      · {p.description}
                    </span>
                  )}
                </div>
              </div>
              {/* Actions */}
              <div className="flex shrink-0 items-center gap-2">
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
                  className="flex size-7 items-center justify-center rounded-lg text-[var(--text-muted)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] transition-colors"
                  aria-label={`Edit ${p.name}`}
                >
                  <PencilSimple aria-hidden weight="bold" className="size-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {formMode && (
        <ProviderForm
          providers={providers}
          mode={formMode}
          onClose={() => setFormMode(null)}
          onSaved={() => void qc.invalidateQueries({ queryKey: ["admin", "ai-providers"] })}
        />
      )}
    </SectionCard>
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
        <div className="flex items-start gap-2 rounded-xl bg-sky-50 px-3 py-2.5 text-sm text-sky-800 border border-sky-200">
          <ShieldWarning aria-hidden weight="fill" className="size-4 shrink-0 mt-0.5" />
          <p>
            Model IDs are stored securely and never returned in API responses or
            shown to non-admin users. Alias names (e.g.{" "}
            <code className="rounded bg-sky-100 px-1 font-mono text-xs">chat_cheap</code>)
            are the only identifiers surfaced to students and partners.
          </p>
        </div>
      </div>
    </Modal>
  );
}

export function AliasesSection({ providers }: { providers: AiProvider[] }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [formMode, setFormMode] = useState<AliasFormMode | null>(null);

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

  return (
    <SectionCard
      title="Model Aliases"
      subtitle="Logical names that route to concrete models at registered providers"
      icon={Robot}
      iconGradient="icon-chip-info"
      action={
        <Button
          variant="secondary"
          onClick={() => setFormMode({ mode: "create" })}
          className="shrink-0"
        >
          <Plus aria-hidden weight="bold" className="size-4" />
          Add alias
        </Button>
      }
    >
      {query.isLoading && (
        <div className="divide-y divide-[var(--border-subtle)]">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-14 animate-pulse bg-[var(--bg-subtle)]" />
          ))}
        </div>
      )}
      {query.isError && (
        <div className="flex items-center gap-2 px-5 py-4 text-sm text-[var(--brand-red)]">
          <XCircle aria-hidden weight="fill" className="size-4 shrink-0" />
          Failed to load aliases.
          <Button variant="ghost" onClick={() => query.refetch()} className="ml-auto">
            <ArrowsClockwise aria-hidden className="size-4" /> Retry
          </Button>
        </div>
      )}
      {!query.isLoading && !query.isError && aliases.length === 0 && (
        <p className="px-5 py-6 text-center text-sm text-[var(--text-muted)]">
          No aliases configured yet.
        </p>
      )}
      {aliases.length > 0 && (
        <div className="divide-y divide-[var(--border-subtle)]">
          {aliases.map((a) => (
            <div
              key={a.id}
              className={cn(
                "flex items-center gap-3 px-5 py-3.5",
                !a.is_active && "opacity-50",
              )}
            >
              {/* Icon */}
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-[var(--ai-accent-soft)] shadow-sm">
                <Robot aria-hidden weight="duotone" className="size-4 text-[var(--ai-accent)]" />
              </span>
              {/* Name + metadata */}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <code className="rounded bg-[var(--bg-subtle)] px-1.5 py-0.5 font-mono text-xs font-semibold text-[var(--text-primary)]">
                    {a.alias_name}
                  </code>
                  {a.is_builtin && <BuiltinBadge />}
                  {!a.is_active && (
                    <StatusBadge tone="closed">
                      <XCircle aria-hidden weight="bold" className="size-3" /> Inactive
                    </StatusBadge>
                  )}
                </div>
                <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-[var(--text-muted)]">
                  {a.provider_name && (
                    <span className="inline-flex items-center gap-1">
                      <Cloud aria-hidden className="size-3" />
                      {a.provider_name}
                    </span>
                  )}
                  {a.task_families && (
                    <span className="inline-flex items-center gap-1">
                      <Tag aria-hidden className="size-3" />
                      {a.task_families}
                    </span>
                  )}
                  {a.description && (
                    <span className="hidden sm:inline text-[var(--text-muted)]">
                      · {a.description}
                    </span>
                  )}
                </div>
              </div>
              {/* Actions */}
              <div className="flex shrink-0 items-center gap-2">
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
                  className="flex size-7 items-center justify-center rounded-lg text-[var(--text-muted)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] transition-colors"
                  aria-label={`Edit alias ${a.alias_name}`}
                >
                  <PencilSimple aria-hidden weight="bold" className="size-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {formMode && (
        <AliasForm
          providers={providers}
          aliases={aliases}
          mode={formMode}
          onClose={() => setFormMode(null)}
          onSaved={() => void qc.invalidateQueries({ queryKey: ["admin", "ai-aliases"] })}
        />
      )}
    </SectionCard>
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
      <div className="flex items-center gap-2 px-1">
        <GearSix aria-hidden weight="duotone" className="size-4 text-[var(--text-muted)]" />
        <span className="text-sm font-semibold text-[var(--text-secondary)]">
          Multi-provider configuration
        </span>
        <span className="ml-auto text-xs text-[var(--text-muted)]">
          Model IDs are never exposed to students or partners
          <ShieldWarning aria-hidden weight="fill" className="inline ml-1 size-3.5 text-[var(--text-muted)]" />
        </span>
      </div>
      <ProvidersSection />
      <AliasesSection providers={providers} />
    </div>
  );
}
