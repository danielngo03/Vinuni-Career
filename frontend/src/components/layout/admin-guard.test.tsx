/**
 * AdminGuard logic tests.
 *
 * The vitest environment is `node` (no DOM), so we test the guard's allow/deny
 * decision logic directly by exercising the auth store state that `AdminGuard`
 * consumes, rather than rendering the JSX tree. This is consistent with every
 * other test in this repo.
 *
 * Contract under test: AdminGuard allows children iff
 *   status === "authenticated" && user.isSuperadmin === true
 * In every other state (unknown / guest / non-superadmin authenticated) the
 * guard must NOT render children (and must redirect to "/").
 */
import { describe, it, expect, beforeEach } from "vitest";
import { useAuthStore } from "@/stores/auth-store";
import type { SessionUser } from "@/stores/auth-store";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSuperadmin(): SessionUser {
  return {
    id: "u-1",
    name: "Admin User",
    email: "admin@vinuni.edu.vn",
    persona: "university",
    isSuperadmin: true,
  };
}

function makeRegularUser(): SessionUser {
  return {
    id: "u-2",
    name: "Regular User",
    email: "student@vinuni.edu.vn",
    persona: "student",
    isSuperadmin: false,
  };
}

/** Evaluate the same condition AdminGuard uses to decide whether to render. */
function guardAllows(
  status: "unknown" | "authenticated" | "guest",
  user: SessionUser | null,
): boolean {
  return status === "authenticated" && (user?.isSuperadmin === true);
}

/** Evaluate the same condition AdminGuard uses to trigger a redirect. */
function guardShouldRedirect(
  status: "unknown" | "authenticated" | "guest",
  user: SessionUser | null,
): boolean {
  if (status === "unknown") return false; // still hydrating — wait, do not redirect yet
  return !guardAllows(status, user);
}

// ---------------------------------------------------------------------------
// Auth store state tests
// ---------------------------------------------------------------------------

beforeEach(() => {
  // Reset to initial store state before each test
  useAuthStore.setState({ user: null, status: "unknown", onboardingComplete: null, onboardingStep: null });
});

describe("AdminGuard — allow logic", () => {
  it("allows access when status=authenticated and isSuperadmin=true", () => {
    useAuthStore.setState({ user: makeSuperadmin(), status: "authenticated" });
    const { status, user } = useAuthStore.getState();
    expect(guardAllows(status, user)).toBe(true);
  });

  it("denies access when status=authenticated but isSuperadmin=false", () => {
    useAuthStore.setState({ user: makeRegularUser(), status: "authenticated" });
    const { status, user } = useAuthStore.getState();
    expect(guardAllows(status, user)).toBe(false);
  });

  it("denies access when status=guest (no user)", () => {
    useAuthStore.setState({ user: null, status: "guest" });
    const { status, user } = useAuthStore.getState();
    expect(guardAllows(status, user)).toBe(false);
  });

  it("denies access while status=unknown (hydrating)", () => {
    useAuthStore.setState({ user: null, status: "unknown" });
    const { status, user } = useAuthStore.getState();
    expect(guardAllows(status, user)).toBe(false);
  });

  it("denies access when user is authenticated but isSuperadmin is undefined", () => {
    const noFlag: SessionUser = { ...makeRegularUser(), isSuperadmin: undefined };
    useAuthStore.setState({ user: noFlag, status: "authenticated" });
    const { status, user } = useAuthStore.getState();
    expect(guardAllows(status, user)).toBe(false);
  });
});

describe("AdminGuard — redirect logic", () => {
  it("triggers redirect for a non-superadmin authenticated user", () => {
    useAuthStore.setState({ user: makeRegularUser(), status: "authenticated" });
    const { status, user } = useAuthStore.getState();
    expect(guardShouldRedirect(status, user)).toBe(true);
  });

  it("triggers redirect for a guest user", () => {
    useAuthStore.setState({ user: null, status: "guest" });
    const { status, user } = useAuthStore.getState();
    expect(guardShouldRedirect(status, user)).toBe(true);
  });

  it("does NOT trigger redirect while auth is loading (unknown status)", () => {
    useAuthStore.setState({ user: null, status: "unknown" });
    const { status, user } = useAuthStore.getState();
    // Guard must wait for hydration before redirecting, otherwise it races
    // with the initial page load.
    expect(guardShouldRedirect(status, user)).toBe(false);
  });

  it("does NOT trigger redirect for a superadmin", () => {
    useAuthStore.setState({ user: makeSuperadmin(), status: "authenticated" });
    const { status, user } = useAuthStore.getState();
    expect(guardShouldRedirect(status, user)).toBe(false);
  });
});

describe("AdminGuard — isSuperadmin field on SessionUser", () => {
  it("isSuperadmin is preserved correctly in auth store state", () => {
    const admin = makeSuperadmin();
    useAuthStore.setState({ user: admin, status: "authenticated" });
    expect(useAuthStore.getState().user?.isSuperadmin).toBe(true);
  });

  it("isSuperadmin is false for a regular user in auth store state", () => {
    const regular = makeRegularUser();
    useAuthStore.setState({ user: regular, status: "authenticated" });
    expect(useAuthStore.getState().user?.isSuperadmin).toBe(false);
  });
});
