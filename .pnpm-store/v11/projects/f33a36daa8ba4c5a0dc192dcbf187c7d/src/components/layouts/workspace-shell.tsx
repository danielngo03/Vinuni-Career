"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import {
  Bell,
  Briefcase,
  Buildings,
  CalendarDots,
  CaretDown,
  ChartBar,
  ChatCircleText,
  ClipboardText,
  FileText,
  Gear,
  House,
  List,
  MagnifyingGlass,
  Robot,
  ShieldCheck,
  SignOut,
  SquaresFour,
  UsersThree,
  X,
} from "@phosphor-icons/react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import type { AuthSession, Portal } from "@/lib/api/types";
import type { Dictionary } from "@/lib/i18n/dictionaries";
import { cn, initials } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AIAssistantPanel } from "@/features/ai/ai-assistant-panel";
import { GlobalSearch } from "@/features/shared/global-search";
import { NotificationCenter } from "@/features/shared/notification-center";
import { apiFetch } from "@/lib/api/client";

type NavItem = {
  label: string;
  href: string;
  icon: typeof House;
};

const portalItems = (
  portal: Portal,
  locale: string,
  dictionary: Dictionary,
): NavItem[] => {
  const base = `/${locale}/${portal}`;
  const common = [
    { label: dictionary.nav.overview, href: base, icon: House },
  ];
  if (portal === "student") {
    return [
      ...common,
      { label: dictionary.nav.jobs, href: `${base}/jobs`, icon: Briefcase },
      { label: dictionary.nav.cv, href: `${base}/cv`, icon: FileText },
      {
        label: dictionary.nav.applications,
        href: `${base}/applications`,
        icon: ClipboardText,
      },
      {
        label: dictionary.nav.interviews,
        href: `${base}/interviews`,
        icon: ChatCircleText,
      },
      { label: dictionary.nav.events, href: `${base}/events`, icon: CalendarDots },
      {
        label: dictionary.nav.reviews,
        href: `${base}/reviews`,
        icon: Buildings,
      },
      { label: dictionary.sections.ai, href: `${base}/ai`, icon: Robot },
    ];
  }
  if (portal === "partner") {
    return [
      ...common,
      { label: dictionary.nav.jobs, href: `${base}/jobs`, icon: Briefcase },
      {
        label: dictionary.nav.candidates,
        href: `${base}/candidates`,
        icon: UsersThree,
      },
      {
        label: dictionary.nav.interviews,
        href: `${base}/interviews`,
        icon: ChatCircleText,
      },
      {
        label: dictionary.nav.analytics,
        href: `${base}/analytics`,
        icon: ChartBar,
      },
      { label: dictionary.sections.ai, href: `${base}/ai`, icon: Robot },
    ];
  }
  return [
    ...common,
    {
      label: dictionary.nav.moderation,
      href: `${base}/moderation`,
      icon: ShieldCheck,
    },
    {
      label: dictionary.nav.organizations,
      href: `${base}/partners`,
      icon: Buildings,
    },
    {
      label: dictionary.nav.analytics,
      href: `${base}/analytics`,
      icon: ChartBar,
    },
    {
      label: dictionary.nav.workflows,
      href: `${base}/workflows`,
      icon: SquaresFour,
    },
    { label: dictionary.sections.registrations, href: `${base}/registrations`, icon: ClipboardText },
    { label: dictionary.sections.ai, href: `${base}/ai`, icon: Robot },
  ];
};

function WorkspaceBrand({ locale }: { locale: string }) {
  return (
    <Link
      href={`/${locale}`}
      className="focus-ring flex items-center gap-3 rounded-lg"
      aria-label="VinUni Career Platform"
    >
      <Image
        src="/brand/vinuni-logo.png"
        alt="VinUni"
        width={161}
        height={152}
        className="h-10 w-auto object-contain"
        priority
      />
      <span className="whitespace-nowrap border-l pl-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">
        Career Platform
      </span>
    </Link>
  );
}

export function WorkspaceShell({
  locale,
  portal,
  session,
  dictionary,
  children,
}: {
  locale: string;
  portal: Portal;
  session: AuthSession;
  dictionary: Dictionary;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const items = useMemo(
    () => portalItems(portal, locale, dictionary),
    [portal, locale, dictionary],
  );

  useEffect(() => {
    apiFetch<{ count: number }>("/notifications/unread-count")
      .then((response) => setUnreadCount(response.count))
      .catch(() => setUnreadCount(0));
  }, []);

  async function switchIdentity(identityId: string) {
    const response = await fetch("/api/auth/identity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identity_id: identityId }),
    });
    if (!response.ok) return;
    const identity = await response.json();
    router.push(`/${locale}/${identity.portal}`);
    router.refresh();
  }

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push(`/${locale}/login`);
    router.refresh();
  }

  function submitSearch(event: React.FormEvent) {
    event.preventDefault();
    if (!search.trim()) return;
    setSearchOpen(true);
  }

  const sidebar = (
    <div className="flex h-full flex-col bg-white">
      <div className="flex h-[72px] items-center justify-between border-b px-5">
        <WorkspaceBrand locale={locale} />
        <button
          type="button"
          className="focus-ring cursor-pointer rounded-lg p-2 lg:hidden"
          onClick={() => setMobileOpen(false)}
          aria-label={dictionary.shell.closeNavigation}
        >
          <X className="size-5" />
        </button>
      </div>
      <nav className="flex-1 overflow-y-auto px-3 py-5" aria-label="Workspace">
        <div className="space-y-1">
          {items.map((item) => {
            const active =
              item.href === pathname ||
              (item.href !== `/${locale}/${portal}` && pathname.startsWith(`${item.href}/`));
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileOpen(false)}
                className={cn(
                  "focus-ring flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                  active
                    ? "bg-blue-50 text-primary"
                    : "text-slate-600 hover:bg-slate-50 hover:text-foreground",
                )}
              >
                <Icon className="size-5" weight={active ? "fill" : "regular"} />
                {item.label}
              </Link>
            );
          })}
        </div>
        <div className="mt-6 border-t pt-5">
          <button
            type="button"
            onClick={() => setNotificationOpen(true)}
            className="focus-ring flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
          >
            <Bell className="size-5" />
            {dictionary.nav.notifications}
            <span className="ml-auto rounded-full bg-primary px-2 py-0.5 text-[10px] font-bold text-white">
              {unreadCount}
            </span>
          </button>
          <button
            type="button"
            onClick={() => setAiOpen(true)}
            className="focus-ring mt-1 flex w-full cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
          >
            <Robot className="size-5" />
            {dictionary.shell.aiAssistant}
          </button>
          <Link
            href={`/${locale}/${portal}/settings`}
            className="focus-ring flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
          >
            <Gear className="size-5" />
            {dictionary.nav.settings}
          </Link>
        </div>
      </nav>
      <div className="border-t p-3">
        <button
          type="button"
          className="focus-ring flex w-full cursor-pointer items-center gap-3 rounded-xl p-2 text-left hover:bg-slate-50"
          onClick={logout}
        >
          <div className="flex size-10 items-center justify-center rounded-full bg-navy text-xs font-bold text-white">
            {initials(session.user.full_name)}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold">{session.user.full_name}</p>
            <p className="truncate text-xs text-muted">
              {session.active_identity?.role_name}
            </p>
          </div>
          <SignOut className="size-4 text-muted" />
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-background">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-[244px] border-r lg:block">
        {sidebar}
      </aside>
      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            className="absolute inset-0 cursor-pointer bg-slate-950/35"
            onClick={() => setMobileOpen(false)}
            aria-label={dictionary.shell.closeNavigation}
          />
          <aside className="relative h-full w-[290px] shadow-2xl">{sidebar}</aside>
        </div>
      ) : null}

      <div className="lg:pl-[244px]">
        <header className="sticky top-0 z-30 flex h-[72px] items-center gap-3 border-b bg-white/95 px-4 backdrop-blur md:px-6">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setMobileOpen(true)}
              aria-label={dictionary.shell.openNavigation}
          >
            <List className="size-5" />
          </Button>
          <form
            onSubmit={submitSearch}
            className="relative hidden max-w-xl flex-1 md:block"
          >
            <MagnifyingGlass className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={dictionary.common.search}
              className="h-10 bg-slate-50 pl-9 shadow-none"
              aria-label={dictionary.common.search}
            />
          </form>
          <div className="ml-auto flex items-center gap-2">
            <DropdownMenu.Root>
              <DropdownMenu.Trigger asChild>
                <Button variant="outline" className="max-w-[210px]">
                  <Buildings className="size-4 text-primary" />
                  <span className="truncate">
                    {session.active_identity?.org_name || dictionary.shell.selectIdentity}
                  </span>
                  <CaretDown className="size-3.5" />
                </Button>
              </DropdownMenu.Trigger>
              <DropdownMenu.Portal>
                <DropdownMenu.Content
                  align="end"
                  className="z-50 min-w-64 rounded-xl border bg-white p-1.5 shadow-xl"
                >
                  {session.identities.map((identity) => (
                    <DropdownMenu.Item
                      key={identity.id}
                      onSelect={() => switchIdentity(identity.id)}
                      className="cursor-pointer rounded-lg px-3 py-2.5 text-sm outline-none hover:bg-slate-50 focus:bg-slate-50"
                    >
                      <p className="font-semibold">{identity.org_name}</p>
                      <p className="text-xs text-muted">
                        {identity.role_name} · {identity.portal}
                      </p>
                    </DropdownMenu.Item>
                  ))}
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
            <Button
              variant="outline"
              size="icon"
              onClick={() =>
                router.push(
                  `/${locale === "vi" ? "en" : "vi"}/${portal}`,
                )
              }
              aria-label={dictionary.common.language}
            >
              <span className="text-xs font-bold">{locale.toUpperCase()}</span>
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-label={dictionary.nav.notifications}
              onClick={() => setNotificationOpen(true)}
              className="relative"
            >
              <Bell className="size-5" />
              {unreadCount > 0 ? (
                <span className="absolute -right-1 -top-1 flex min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[9px] font-bold text-white ring-2 ring-white">
                  {unreadCount > 99 ? "99+" : unreadCount}
                </span>
              ) : null}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-label={dictionary.shell.aiAssistant}
              onClick={() => setAiOpen(true)}
              className="hidden sm:inline-flex"
            >
              <Robot className="size-5" weight="duotone" />
            </Button>
            <div className="hidden size-9 items-center justify-center rounded-full bg-navy text-xs font-bold text-white sm:flex">
              {initials(session.user.full_name)}
            </div>
          </div>
        </header>
        <main>{children}</main>
      </div>
      <GlobalSearch
        key={search}
        open={searchOpen}
        onOpenChange={setSearchOpen}
        initialQuery={search}
      />
      <NotificationCenter
        open={notificationOpen}
        onOpenChange={setNotificationOpen}
        onUnreadChange={setUnreadCount}
      />
      <AIAssistantPanel open={aiOpen} onOpenChange={setAiOpen} />
    </div>
  );
}
