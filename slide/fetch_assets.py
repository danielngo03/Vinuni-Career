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
    "student":      ("solar:square-academic-cap-2-bold-duotone", "#2563eb"),
    "recruiter":    ("solar:case-round-bold-duotone",            "#0d9488"),
    "university":   ("solar:buildings-3-bold-duotone",           "#d97706"),
    "marketplace":  ("solar:compass-bold-duotone",               "#2563eb"),
    "dashboard":    ("solar:widget-5-bold-duotone",              "#4f46e5"),
    "partner":      ("solar:case-minimalistic-bold-duotone",     "#0d9488"),
    "govern":       ("solar:buildings-2-bold-duotone",           "#d97706"),
    # AI / product
    "ai":           ("solar:cpu-bolt-bold-duotone",              "#4f46e5"),
    "bot":          ("solar:chat-round-dots-bold-duotone",       "#0ea5e9"),
    "cv":           ("solar:document-text-bold-duotone",         "#7c3aed"),
    "match":        ("solar:target-bold-duotone",                "#c8102e"),
    "pipeline":     ("solar:clipboard-list-bold-duotone",        "#0d9488"),
    "interview":    ("solar:microphone-3-bold-duotone",          "#4f46e5"),
    "talent":       ("solar:users-group-two-rounded-bold-duotone","#0d9488"),
    "workflow":     ("solar:routing-2-bold-duotone",             "#7c3aed"),
    "moderate":     ("solar:shield-check-bold-duotone",          "#16a34a"),
    # business
    "market":       ("solar:chart-2-bold-duotone",               "#16a34a"),
    "money":        ("solar:wallet-money-bold-duotone",          "#16a34a"),
    "revenue":      ("solar:banknote-2-bold-duotone",            "#16a34a"),
    "ads":          ("solar:posts-carousel-vertical-bold-duotone","#d97706"),
    "growth":       ("solar:rocket-2-bold-duotone",              "#c8102e"),
    "globe":        ("solar:global-bold-duotone",                "#2563eb"),
    "target":       ("solar:target-bold-duotone",                "#c8102e"),
    "trend":        ("solar:graph-up-bold-duotone",              "#16a34a"),
    "scale":        ("solar:layers-bold-duotone",                "#4f46e5"),
    "check":        ("solar:verified-check-bold-duotone",        "#16a34a"),
    "medal":        ("solar:medal-star-bold-duotone",            "#d97706"),
    # infra / arch
    "shield":       ("solar:shield-keyhole-bold-duotone",        "#16a34a"),
    "database":     ("solar:database-bold-duotone",              "#2563eb"),
    "cloud":        ("solar:cloud-storage-bold-duotone",         "#0ea5e9"),
    "settings":     ("solar:settings-bold-duotone",              "#5b6472"),
    "layers":       ("solar:layers-minimalistic-bold-duotone",   "#16386b"),
    "server":       ("solar:server-2-bold-duotone",              "#16386b"),
    "lock":         ("solar:lock-keyhole-minimalistic-bold-duotone","#c8102e"),
    "users":        ("solar:users-group-rounded-bold-duotone",   "#2563eb"),
    "calendar":     ("solar:calendar-mark-bold-duotone",         "#d97706"),
    "chat":         ("solar:chat-square-like-bold-duotone",      "#0ea5e9"),
    "search":       ("solar:magnifer-bold-duotone",              "#2563eb"),
    "idea":         ("solar:lightbulb-bolt-bold-duotone",        "#d97706"),
    "flag":         ("solar:flag-2-bold-duotone",                "#c8102e"),
    "clock":        ("solar:clock-circle-bold-duotone",          "#5b6472"),
    "star":         ("solar:star-bold",                          "#d97706"),
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
