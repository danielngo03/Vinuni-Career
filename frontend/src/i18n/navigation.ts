import { createNavigation } from "next-intl/navigation";
import { routing } from "./routing";

// Locale-aware navigation helpers. Always import Link/useRouter/redirect from here.
export const { Link, redirect, usePathname, useRouter, getPathname } =
  createNavigation(routing);
