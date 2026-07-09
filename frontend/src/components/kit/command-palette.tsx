"use client";

import * as React from "react";
import { useRouter } from "@/i18n/navigation";
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from "@/components/ui/command";

export interface CommandAction {
  key: string;
  label: string;
  /** Navigate here on select (absolute app path). Mutually exclusive with onSelect. */
  href?: string;
  onSelect?: () => void;
  icon?: React.ElementType;
  /** Group heading (small-caps). Items with the same group are clustered. */
  group?: string;
  /** Extra search terms. */
  keywords?: string[];
}

/**
 * CommandPalette — the ⌘K launcher (shadcn command + dialog). Controlled via
 * `open`/`onOpenChange`; also registers the ⌘K / Ctrl+K global shortcut so
 * consumers only render it once (e.g. in the Topbar). Items deep-link into real
 * routes or run a callback.
 */
export function CommandPalette({
  open,
  onOpenChange,
  actions,
  placeholder,
  emptyLabel,
  title,
  description,
  /** Register the global ⌘K shortcut (default true). */
  enableShortcut = true,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  actions: CommandAction[];
  placeholder: string;
  emptyLabel: string;
  title: string;
  description?: string;
  enableShortcut?: boolean;
}) {
  const router = useRouter();

  React.useEffect(() => {
    if (!enableShortcut) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        onOpenChange(!open);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onOpenChange, enableShortcut]);

  // Preserve group order as first-seen.
  const groups = React.useMemo(() => {
    const order: string[] = [];
    const map = new Map<string, CommandAction[]>();
    for (const a of actions) {
      const g = a.group ?? "";
      if (!map.has(g)) {
        map.set(g, []);
        order.push(g);
      }
      map.get(g)!.push(a);
    }
    return order.map((g) => ({ group: g, items: map.get(g)! }));
  }, [actions]);

  function run(action: CommandAction) {
    onOpenChange(false);
    if (action.onSelect) action.onSelect();
    else if (action.href) router.push(action.href);
  }

  return (
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={description ?? placeholder}
    >
      <CommandInput placeholder={placeholder} />
      <CommandList>
        <CommandEmpty>{emptyLabel}</CommandEmpty>
        {groups.map(({ group, items }) => (
          <CommandGroup key={group || "_"} heading={group || undefined}>
            {items.map((action) => {
              const Icon = action.icon;
              return (
                <CommandItem
                  key={action.key}
                  value={`${action.label} ${(action.keywords ?? []).join(" ")}`}
                  onSelect={() => run(action)}
                >
                  {Icon && <Icon className="size-4 text-muted-foreground" strokeWidth={1.8} />}
                  {action.label}
                </CommandItem>
              );
            })}
          </CommandGroup>
        ))}
      </CommandList>
    </CommandDialog>
  );
}
