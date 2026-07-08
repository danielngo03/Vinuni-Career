"use client";

import { useTranslations } from "next-intl";
import { WORKSPACE_NAV, type WorkspacePersona } from "@/config/nav";
import { ComingSoon } from "./coming-soon";

/**
 * Resolves a human title for an as-yet-unbuilt workspace route and renders the
 * honest under-construction state. Used by the persona catch-all so every nav
 * destination resolves to a real shell page (no 404, no fake dashboard).
 */
export function WorkspacePlaceholder({
  persona,
  slug,
}: {
  persona: WorkspacePersona;
  slug: string[];
}) {
  const tNav = useTranslations("nav");
  const tShell = useTranslations("shell");

  const path = `/${slug.join("/")}`;
  const match = WORKSPACE_NAV[persona].find(
    (item) => path === item.href || path.startsWith(`${item.href}/`),
  );

  const title = match ? tNav(match.key) : tShell("comingSoonTitle");
  return <ComingSoon title={title} />;
}
