#!/usr/bin/env python3
"""Download real design assets (Solar duotone icons recolored to brand + full-colour
tech logos) from the Iconify API into slide/assets/lib/. Run once; build_deck.py
inlines the saved SVGs. Prints a manifest of what was fetched vs missing."""
import urllib.request, urllib.parse, pathlib, time

LIB = pathlib.Path(__file__).parent / "assets" / "lib"
LIB.mkdir(parents=True, exist_ok=True)
BASE = "https://api.iconify.design/{}.svg"

# concept -> (iconify id, hex colour for duotone; None = keep native colour e.g. logos)
ICONS = {
    # personas / surfaces
    "student":      ("solar:square-academic-cap-2-bold-duotone", "#0ea5e9"),
    "recruiter":    ("solar:case-round-bold-duotone",            "#14b8a6"),
    "university":   ("solar:buildings-3-bold-duotone",           "#f59e0b"),
    "marketplace":  ("solar:compass-bold-duotone",               "#0ea5e9"),
    "dashboard":    ("solar:widget-5-bold-duotone",              "#6366f1"),
    "partner":      ("solar:case-minimalistic-bold-duotone",     "#14b8a6"),
    "govern":       ("solar:buildings-2-bold-duotone",           "#f59e0b"),
    # AI / product
    "ai":           ("solar:cpu-bolt-bold-duotone",              "#6366f1"),
    "bot":          ("solar:chat-round-dots-bold-duotone",       "#0ea5e9"),
    "cv":           ("solar:document-text-bold-duotone",         "#8b5cf6"),
    "match":        ("solar:target-bold-duotone",                "#f43f5e"),
    "pipeline":     ("solar:clipboard-list-bold-duotone",        "#14b8a6"),
    "interview":    ("solar:microphone-3-bold-duotone",          "#6366f1"),
    "talent":       ("solar:users-group-two-rounded-bold-duotone","#14b8a6"),
    "workflow":     ("solar:routing-2-bold-duotone",             "#8b5cf6"),
    "moderate":     ("solar:shield-check-bold-duotone",          "#10b981"),
    # business
    "market":       ("solar:chart-2-bold-duotone",               "#10b981"),
    "money":        ("solar:wallet-money-bold-duotone",          "#10b981"),
    "revenue":      ("solar:banknote-2-bold-duotone",            "#10b981"),
    "ads":          ("solar:posts-carousel-vertical-bold-duotone","#f59e0b"),
    "growth":       ("solar:rocket-2-bold-duotone",              "#f43f5e"),
    "globe":        ("solar:global-bold-duotone",                "#0ea5e9"),
    "target":       ("solar:target-bold-duotone",                "#f43f5e"),
    "trend":        ("solar:graph-up-bold-duotone",              "#10b981"),
    "scale":        ("solar:layers-bold-duotone",                "#6366f1"),
    "check":        ("solar:verified-check-bold-duotone",        "#10b981"),
    "medal":        ("solar:medal-star-bold-duotone",            "#f59e0b"),
    # infra / arch
    "shield":       ("solar:shield-keyhole-bold-duotone",        "#10b981"),
    "database":     ("solar:database-bold-duotone",              "#0ea5e9"),
    "cloud":        ("solar:cloud-storage-bold-duotone",         "#0ea5e9"),
    "settings":     ("solar:settings-bold-duotone",              "#52525b"),
    "layers":       ("solar:layers-minimalistic-bold-duotone",   "#171717"),
    "server":       ("solar:server-2-bold-duotone",              "#171717"),
    "lock":         ("solar:lock-keyhole-minimalistic-bold-duotone","#f43f5e"),
    "users":        ("solar:users-group-rounded-bold-duotone",   "#0ea5e9"),
    "calendar":     ("solar:calendar-mark-bold-duotone",         "#f59e0b"),
    "chat":         ("solar:chat-square-like-bold-duotone",      "#0ea5e9"),
    "search":       ("solar:magnifer-bold-duotone",              "#0ea5e9"),
    "idea":         ("solar:lightbulb-bolt-bold-duotone",        "#f59e0b"),
    "flag":         ("solar:flag-2-bold-duotone",                "#f43f5e"),
    "clock":        ("solar:clock-circle-bold-duotone",          "#52525b"),
    "star":         ("solar:star-bold",                          "#f59e0b"),
}

LOGOS = ["postgresql", "redis", "nextjs-icon", "fastapi-icon", "python", "react",
         "typescript-icon", "tailwindcss-icon", "openai-icon", "digital-ocean-icon",
         "docker-icon", "sentry-icon", "celery-icon", "sqlalchemy", "google-icon"]


def fetch(url, dest):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=12).read()
        if data[:4] != b"<svg" or b"Not found" in data[:40]:
            return False
        dest.write_bytes(data)
        return True
    except Exception:
        return False


def main():
    ok, miss = [], []
    for name, (iid, color) in ICONS.items():
        url = BASE.format(iid)
        if color:
            url += "?" + urllib.parse.urlencode({"color": color})
        (ok if fetch(url, LIB / f"ic-{name}.svg") else miss).append(name)
        time.sleep(0.12)
    lok, lmiss = [], []
    for lg in LOGOS:
        (lok if fetch(BASE.format(f"logos:{lg}"), LIB / f"logo-{lg}.svg") else lmiss).append(lg)
        time.sleep(0.12)
    print(f"icons ok ({len(ok)}): {' '.join(ok)}")
    print(f"icons MISSING ({len(miss)}): {' '.join(miss)}")
    print(f"logos ok ({len(lok)}): {' '.join(lok)}")
    print(f"logos MISSING ({len(lmiss)}): {' '.join(lmiss)}")


if __name__ == "__main__":
    main()
