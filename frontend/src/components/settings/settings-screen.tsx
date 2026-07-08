"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import {
  GearSix,
  BellRinging,
  Devices,
  ShieldCheck,
  LockKey,
} from "@phosphor-icons/react";
import { TabPanel, type TabItem } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { GeneralTab } from "./general-tab";
import { NotificationsTab } from "./notifications-tab";
import { DevicesTab } from "./devices-tab";
import { SecurityTab } from "./security-tab";
import { PrivacyTab } from "./privacy-tab";
import { cn } from "@/lib/utils";

const TABS_ID = "settings";

/**
 * Reusable account settings shell (NOTIFICATIONS_COMMUNICATIONS_SPEC §5–6).
 * Covers language, timezone, theme, notification preferences, active
 * sessions/devices, and security events. Used across personas.
 */
export function SettingsScreen() {
  const t = useTranslations("settings");
  const [tab, setTab] = useState("general");
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  const items: TabItem[] = [
    {
      value: "general",
      label: t("tabs.general"),
      icon: <GearSix aria-hidden weight="duotone" className="size-4" />,
    },
    {
      value: "notifications",
      label: t("tabs.notifications"),
      icon: <BellRinging aria-hidden weight="duotone" className="size-4" />,
    },
    {
      value: "devices",
      label: t("tabs.devices"),
      icon: <Devices aria-hidden weight="duotone" className="size-4" />,
    },
    {
      value: "security",
      label: t("tabs.security"),
      icon: <ShieldCheck aria-hidden weight="duotone" className="size-4" />,
    },
    {
      value: "privacy",
      label: t("tabs.privacy"),
      icon: <LockKey aria-hidden weight="duotone" className="size-4" />,
    },
  ];

  function onKeyDown(e: React.KeyboardEvent) {
    const idx = items.findIndex((i) => i.value === tab);
    if (idx === -1) return;

    let next = idx;
    if (e.key === "ArrowDown" || e.key === "ArrowRight") next = (idx + 1) % items.length;
    else if (e.key === "ArrowUp" || e.key === "ArrowLeft") next = (idx - 1 + items.length) % items.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = items.length - 1;
    else return;

    e.preventDefault();
    const target = items[next]!;
    setTab(target.value);
    refs.current[target.value]?.focus();
  }

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title={t("title")} />
      <div className="grid gap-5 lg:grid-cols-[220px_minmax(0,1fr)] lg:items-start lg:gap-8">
        <aside
          role="tablist"
          aria-label={t("title")}
          onKeyDown={onKeyDown}
          className="lg:sticky lg:top-[84px]"
        >
          <div className="flex gap-1 overflow-x-auto rounded-[18px] bg-[#f7f6f2] p-1.5 shadow-[inset_0_0_0_1px_rgba(0,0,0,0.045)] lg:flex-col lg:overflow-visible">
            {items.map((item) => {
              const selected = item.value === tab;
              return (
                <button
                  key={item.value}
                  ref={(el) => {
                    refs.current[item.value] = el;
                  }}
                  type="button"
                  role="tab"
                  id={`${TABS_ID}-tab-${item.value}`}
                  aria-selected={selected}
                  aria-controls={`${TABS_ID}-panel-${item.value}`}
                  tabIndex={selected ? 0 : -1}
                  onClick={() => setTab(item.value)}
                  className={cn(
                    "inline-flex min-h-10 shrink-0 cursor-pointer items-center gap-2.5 rounded-[13px] px-3 py-2 text-sm font-semibold outline-none transition-all duration-200 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/25 lg:w-full",
                    selected
                      ? "bg-[var(--text-primary)] text-white shadow-[0_8px_18px_rgba(0,0,0,0.12)]"
                      : "text-[var(--text-secondary)] hover:bg-white hover:text-[var(--text-primary)]",
                  )}
                >
                  <span
                    className={cn(
                      "shrink-0",
                      selected ? "text-white" : "text-[var(--text-muted)]",
                    )}
                  >
                    {item.icon}
                  </span>
                  <span className="whitespace-nowrap">{item.label}</span>
                </button>
              );
            })}
          </div>
        </aside>

        <div className="min-w-0">
          <TabPanel tabsId={TABS_ID} value="general" active={tab === "general"}>
            <GeneralTab />
          </TabPanel>
          <TabPanel
            tabsId={TABS_ID}
            value="notifications"
            active={tab === "notifications"}
          >
            <NotificationsTab />
          </TabPanel>
          <TabPanel tabsId={TABS_ID} value="devices" active={tab === "devices"}>
            <DevicesTab />
          </TabPanel>
          <TabPanel tabsId={TABS_ID} value="security" active={tab === "security"}>
            <SecurityTab />
          </TabPanel>
          <TabPanel tabsId={TABS_ID} value="privacy" active={tab === "privacy"}>
            <PrivacyTab />
          </TabPanel>
        </div>
      </div>
    </div>
  );
}
