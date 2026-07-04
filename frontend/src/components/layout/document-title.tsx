"use client";

import { useEffect } from "react";
import { useLocale } from "next-intl";
import { usePathname } from "@/i18n/navigation";
import { composeDocumentTitle, getRouteTitle } from "@/lib/route-titles";

export function DocumentTitle() {
  const locale = useLocale();
  const pathname = usePathname();

  useEffect(() => {
    document.title = composeDocumentTitle(getRouteTitle(pathname, locale));
  }, [locale, pathname]);

  return null;
}
