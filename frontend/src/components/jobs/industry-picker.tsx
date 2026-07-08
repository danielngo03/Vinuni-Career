"use client";

import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocale } from "next-intl";
import {
  CaretDown,
  CaretRight,
  Check,
  MagnifyingGlass,
  X,
} from "@phosphor-icons/react";
import { searchApi, type IndustryBranch, type IndustryLeaf, type IndustryRoot } from "@/lib/api/search";
import { cn } from "@/lib/utils";
import {
  flattenIndustries,
  findIndustry,
  normalize,
  type FlatIndustry,
} from "@/lib/jobs/industry-lookup";

export interface IndustryPickerProps {
  value: string | null;
  onChange: (id: string | null) => void;
  /** When omitted the picker renders no visible label (caller owns the label). */
  label?: string;
  placeholder: string;
  searchPlaceholder: string;
  emptyText: string;
  loadingText: string;
  /** Which name/path to display. Defaults to the current next-intl locale. */
  locale?: "vi" | "en";
  disabled?: boolean;
  helpText?: string;
}

const LEVEL_LABELS: Record<number, { vi: string; en: string }> = {
  0: { vi: "Ngành", en: "Sector" },
  1: { vi: "Nhóm", en: "Branch" },
  2: { vi: "Chuyên ngành", en: "Specialization" },
};

function levelLabel(level: number, locale: "vi" | "en"): string {
  return LEVEL_LABELS[level]?.[locale] ?? "";
}

function industryName(
  node: Pick<IndustryLeaf, "name_vi" | "name_en">,
  locale: "vi" | "en",
): string {
  return locale === "vi" ? node.name_vi : node.name_en;
}

function industryMatches(
  node: Pick<IndustryLeaf, "name_vi" | "name_en">,
  locale: "vi" | "en",
  term: string,
): boolean {
  if (!term.trim()) return true;
  const needle = normalize(term);
  return (
    normalize(industryName(node, locale)).includes(needle) ||
    normalize(`${node.name_vi} ${node.name_en}`).includes(needle)
  );
}

export function IndustryPicker({
  value,
  onChange,
  label,
  placeholder,
  searchPlaceholder,
  emptyText,
  loadingText,
  locale: localeProp,
  disabled,
  helpText,
}: IndustryPickerProps) {
  const resolvedLocaleRaw = useLocale();
  const resolvedLocale: "vi" | "en" =
    localeProp ?? (resolvedLocaleRaw === "vi" ? "vi" : "en");

  const pickerId = useId();
  const labelId = `${pickerId}-label`;
  const helpId = `${pickerId}-help`;
  const listboxId = `${pickerId}-listbox`;
  const searchId = `${pickerId}-search`;

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeRootId, setActiveRootId] = useState("");
  const [activeBranchId, setActiveBranchId] = useState("");

  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  // ── Data ────────────────────────────────────────────────────────────────────
  const { data: tree, isLoading } = useQuery({
    queryKey: ["industries", "tree"],
    queryFn: () => searchApi.industryTree(),
    staleTime: 10 * 60 * 1000,
    retry: false,
  });

  const flat: FlatIndustry[] = tree ? flattenIndustries(tree) : [];
  const selected = findIndustry(flat, value);
  const selectedPath = selected
    ? resolvedLocale === "vi"
      ? selected.pathVi
      : selected.pathEn
    : null;

  // ── Helpers ─────────────────────────────────────────────────────────────────
  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
  }, []);

  const select = useCallback(
    (id: string) => {
      onChange(id);
      close();
      triggerRef.current?.focus();
    },
    [onChange, close],
  );

  const clear = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      onChange(null);
    },
    [onChange],
  );

  // ── Open/close behavior ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!open) return;

    // Focus search on open
    const id = window.setTimeout(() => {
      searchRef.current?.focus();
    }, 0);

    // Click-outside closes
    function handlePointerDown(e: PointerEvent) {
      const target = e.target as Node;
      if (!panelRef.current?.contains(target) && !triggerRef.current?.contains(target)) {
        close();
      }
    }

    // Escape closes
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        close();
        triggerRef.current?.focus();
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      clearTimeout(id);
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open, close]);

  const filteredRoots = useMemo(
    () =>
      (tree ?? []).filter((root) => {
        if (industryMatches(root, resolvedLocale, query)) return true;
        return root.children.some((branch) => {
          if (industryMatches(branch, resolvedLocale, query)) return true;
          return branch.children.some((leaf) =>
            industryMatches(leaf, resolvedLocale, query),
          );
        });
      }),
    [tree, resolvedLocale, query],
  );

  const activeRoot = useMemo(() => {
    if (filteredRoots.length === 0) return null;
    return (
      filteredRoots.find((root) => root.id === activeRootId) ?? filteredRoots[0]
    );
  }, [filteredRoots, activeRootId]);

  const branches = useMemo(() => {
    if (!activeRoot) return [] as IndustryBranch[];
    if (!query.trim()) return activeRoot.children;
    return activeRoot.children.filter((branch) => {
      if (industryMatches(branch, resolvedLocale, query)) return true;
      return branch.children.some((leaf) => industryMatches(leaf, resolvedLocale, query));
    });
  }, [activeRoot, query, resolvedLocale]);

  const activeBranch = useMemo(() => {
    if (branches.length === 0) return null;
    return branches.find((branch) => branch.id === activeBranchId) ?? branches[0];
  }, [branches, activeBranchId]);

  const leaves = useMemo(() => {
    if (!activeBranch) return [] as IndustryLeaf[];
    if (!query.trim()) return activeBranch.children;
    return activeBranch.children.filter((leaf) =>
      industryMatches(leaf, resolvedLocale, query),
    );
  }, [activeBranch, query, resolvedLocale]);

  useEffect(() => {
    if (!open) return;

    if (value && tree?.length) {
      for (const root of tree) {
        if (root.id === value) {
          setActiveRootId(root.id);
          setActiveBranchId("");
          return;
        }
        for (const branch of root.children) {
          if (branch.id === value) {
            setActiveRootId(root.id);
            setActiveBranchId(branch.id);
            return;
          }
          if (branch.children.some((leaf) => leaf.id === value)) {
            setActiveRootId(root.id);
            setActiveBranchId(branch.id);
            return;
          }
        }
      }
    }

    const firstRoot = filteredRoots[0];
    const firstBranch = branches[0];
    if (firstRoot) setActiveRootId((prev) => prev || firstRoot.id);
    if (firstBranch) setActiveBranchId((prev) => prev || firstBranch.id);
  }, [open, value, tree, filteredRoots, branches]);

  // ── Trigger display text ─────────────────────────────────────────────────────
  const triggerText = selected ? industryName(selected, resolvedLocale) : placeholder;
  const triggerMuted = !selected;

  function nodeButton(
    node: IndustryRoot | IndustryBranch | IndustryLeaf,
    options?: {
      active?: boolean;
      onActivate?: () => void;
      showArrow?: boolean;
    },
  ) {
    const checked = node.id === value;
    return (
      <button
        key={node.id}
        type="button"
        onMouseEnter={options?.onActivate}
        onFocus={options?.onActivate}
        onClick={() => {
          options?.onActivate?.();
          select(node.id);
        }}
        className={cn(
          "flex w-full items-center gap-3 rounded-xl px-2.5 py-2.5 text-left transition-colors hover:bg-[var(--surface-secondary)]",
          options?.active && "bg-[var(--surface-secondary)]",
          checked && "bg-[var(--surface-secondary)] text-[var(--text-primary)]",
        )}
      >
        <span
          className={cn(
            "flex size-5 shrink-0 items-center justify-center rounded-md border",
            checked
              ? "border-[var(--text-primary)] bg-[var(--text-primary)] text-[var(--surface-card)]"
              : "border-[var(--border-default)] bg-[var(--surface-card)]",
          )}
        >
          {checked && <Check aria-hidden weight="bold" className="size-3.5" />}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold text-[var(--text-primary)]">
            {industryName(node, resolvedLocale)}
          </span>
          {"level" in node && levelLabel(node.level, resolvedLocale) && (
            <span className="block text-[11px] text-[var(--text-muted)]">
              {levelLabel(node.level, resolvedLocale)}
            </span>
          )}
        </span>
        {options?.showArrow && (
          <CaretRight
            aria-hidden
            weight="bold"
            className="size-4 shrink-0 text-[var(--text-muted)]"
          />
        )}
      </button>
    );
  }

  return (
    <div className="relative w-full">
      {/* Label — only rendered when the caller passes a label prop.
          When absent, the caller owns the visible label; the trigger still
          uses aria-label so screen readers have a name. */}
      {label && (
        <p
          id={labelId}
          className="mb-1.5 text-sm font-semibold text-[var(--text-primary)]"
        >
          {label}
        </p>
      )}

      {/* Trigger button */}
      <button
        ref={triggerRef}
        type="button"
        id={pickerId}
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-labelledby={label ? labelId : undefined}
        aria-label={!label ? placeholder : undefined}
        aria-describedby={helpText ? helpId : undefined}
        disabled={disabled}
        onClick={() => {
          if (!open) setOpen(true);
          else close();
        }}
        className={cn(
          "flex h-10 w-full items-center justify-between gap-2 rounded-xl border px-3.5 text-sm font-medium",
          "bg-transparent outline-none transition-[border-color,box-shadow] duration-150",
          "focus-visible:border-[var(--field-focus-border)] focus-visible:shadow-[0_0_0_4px_var(--field-focus-ring)]",
          open
            ? "border-[var(--field-focus-border)] shadow-[0_0_0_4px_var(--field-focus-ring)]"
            : "border-[var(--border-default)] hover:border-[var(--border-strong)]",
          "disabled:cursor-not-allowed disabled:opacity-60",
        )}
      >
        <span
          className={cn(
            "min-w-0 flex-1 truncate text-left",
            triggerMuted ? "text-[var(--text-muted)]" : "text-[var(--text-primary)]",
          )}
        >
          {triggerText}
        </span>

        <span className="flex shrink-0 items-center gap-1">
          {selected && !disabled && (
            <span
              role="button"
              tabIndex={0}
              aria-label="Clear selection"
              onClick={clear}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onChange(null);
                }
              }}
              className="rounded-md p-0.5 text-[var(--text-muted)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)]"
            >
              <X aria-hidden weight="bold" className="size-3.5" />
            </span>
          )}
          <CaretDown
            aria-hidden
            weight="bold"
            className={cn(
              "size-4 text-[var(--text-muted)] transition-transform duration-150",
              open && "rotate-180",
            )}
          />
        </span>
      </button>

      {/* Help text */}
      {helpText && (
        <p id={helpId} className="mt-1 text-xs text-[var(--text-secondary)]">
          {helpText}
        </p>
      )}
      {selectedPath && !helpText && (
        <p className="mt-1 truncate text-xs text-[var(--text-secondary)]">
          {selectedPath}
        </p>
      )}

      {/* Dropdown panel */}
      {open && (
        <div
          ref={panelRef}
          className={cn(
            "absolute left-0 top-full z-50 mt-2 overflow-hidden rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] shadow-[0_24px_70px_rgba(11,34,57,0.16)]",
            "w-[min(920px,calc(100vw-2rem))] max-w-[calc(100vw-2rem)]",
          )}
          // Prevent the click-outside listener from closing when interacting inside
          onPointerDown={(e) => e.stopPropagation()}
        >
          {/* Search */}
          <div className="border-b border-[var(--border-default)] px-3 py-2">
            <div className="flex items-center gap-2">
              <MagnifyingGlass
                aria-hidden
                weight="bold"
                className="size-4 shrink-0 text-[var(--text-muted)]"
              />
              <input
                ref={searchRef}
                id={searchId}
                type="text"
                role="searchbox"
                aria-label={searchPlaceholder}
                aria-controls={listboxId}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={searchPlaceholder}
                className="flex-1 bg-transparent text-sm font-medium text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
              />
              {query && (
                <button
                  type="button"
                  aria-label="Clear search"
                  onClick={() => {
                    setQuery("");
                    searchRef.current?.focus();
                  }}
                  className="rounded-md p-0.5 text-[var(--text-muted)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)]"
                >
                  <X aria-hidden weight="bold" className="size-3.5" />
                </button>
              )}
            </div>
          </div>

          <div
            id={listboxId}
            role="listbox"
            aria-label={label}
            className="grid min-h-[360px] md:grid-cols-[1fr_1fr_1.1fr]"
          >
            <div className="border-b border-[var(--border-default)] p-4 md:border-b-0 md:border-r">
              <p className="mb-3 text-xs font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                {resolvedLocale === "vi" ? "Ngành" : "Sector"}
              </p>
              <div className="max-h-[300px] space-y-1 overflow-y-auto pr-1">
                {isLoading ? (
                  <p className="px-2.5 py-2 text-sm text-[var(--text-muted)]">{loadingText}</p>
                ) : filteredRoots.length === 0 ? (
                  <p className="rounded-2xl bg-[var(--surface-secondary)] p-4 text-sm font-medium text-[var(--text-muted)]">
                    {emptyText}
                  </p>
                ) : (
                  filteredRoots.map((root) =>
                    nodeButton(root, {
                      active: activeRoot?.id === root.id,
                      showArrow: root.children.length > 0,
                      onActivate: () => {
                        setActiveRootId(root.id);
                        setActiveBranchId("");
                      },
                    }),
                  )
                )}
              </div>
            </div>

            <div className="border-b border-[var(--border-default)] p-4 md:border-b-0 md:border-r">
              <p className="mb-3 text-xs font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                {resolvedLocale === "vi" ? "Nhóm ngành" : "Branch"}
              </p>
              <div className="max-h-[300px] space-y-1 overflow-y-auto pr-1">
                {branches.length > 0 ? (
                  branches.map((branch) =>
                    nodeButton(branch, {
                      active: activeBranch?.id === branch.id,
                      showArrow: branch.children.length > 0,
                      onActivate: () => setActiveBranchId(branch.id),
                    }),
                  )
                ) : (
                  <p className="rounded-2xl bg-[var(--surface-secondary)] p-4 text-sm font-medium text-[var(--text-muted)]">
                    {resolvedLocale === "vi"
                      ? "Chọn một ngành để xem nhóm ngành phù hợp."
                      : "Choose a sector to browse its branches."}
                  </p>
                )}
              </div>
            </div>

            <div className="p-4">
              <p className="mb-3 text-xs font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                {resolvedLocale === "vi" ? "Chuyên ngành" : "Specialization"}
              </p>
              <div className="max-h-[300px] space-y-1 overflow-y-auto pr-1">
                {leaves.length > 0 ? (
                  leaves.map((leaf) => nodeButton(leaf))
                ) : activeBranch ? (
                  <button
                    type="button"
                    onClick={() => select(activeBranch.id)}
                    className="w-full rounded-2xl border border-dashed border-[var(--border-default)] bg-[var(--surface-secondary)] px-4 py-4 text-left transition-colors hover:border-[var(--border-strong)]"
                  >
                    <span className="block text-sm font-semibold text-[var(--text-primary)]">
                      {industryName(activeBranch, resolvedLocale)}
                    </span>
                    <span className="mt-1 block text-xs text-[var(--text-muted)]">
                      {resolvedLocale === "vi"
                        ? "Nhóm ngành này không có chuyên ngành con. Nhấn để chọn trực tiếp."
                        : "This branch has no child specializations. Click to select it directly."}
                    </span>
                  </button>
                ) : (
                  <p className="rounded-2xl bg-[var(--surface-secondary)] p-4 text-sm font-medium text-[var(--text-muted)]">
                    {resolvedLocale === "vi"
                      ? "Chọn nhóm ngành để hoàn tất lựa chọn."
                      : "Choose a branch to finish the selection."}
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
