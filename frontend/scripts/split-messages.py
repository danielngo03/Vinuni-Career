#!/usr/bin/env python3
"""One-time migration: split monolithic en.json/vi.json into per-domain files
under src/messages/{locale}/{group}/{file}.json, folding in the existing
en/cv.json, en/jobs.json (and vi equivalents) overlay patches so there is a
single source of truth per namespace.

Safe to re-run: it always rebuilds domain files from the current monolith +
patches, and does not hand-edit any content.
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MSG_DIR = os.path.join(BASE, "src", "messages")

LOCALES = ["en", "vi"]

# namespace -> (group, filename without .json)
MAPPING = {
    # shared
    "common": ("shared", "common"),
    "states": ("shared", "common"),
    "errors": ("shared", "common"),
    "labels": ("shared", "common"),
    "nav": ("shared", "shell"),
    "shell": ("shared", "shell"),
    "footer": ("shared", "shell"),
    # public marketplace / discovery
    "landing": ("public", "landing"),
    "personas": ("public", "landing"),
    "careerExplore": ("public", "landing"),
    "marketplace": ("public", "marketplace"),
    "companies": ("public", "marketplace"),
    "companyMenu": ("public", "marketplace"),
    "employers": ("public", "marketplace"),
    "discovery": ("public", "marketplace"),
    "events": ("public", "events"),
    # auth
    "auth": ("auth", "auth"),
    "activate": ("auth", "auth"),
    "inviteAccept": ("auth", "auth"),
    "partnerReg": ("auth", "auth"),
    # student
    "dashboard": ("student", "dashboard"),
    "profile": ("student", "profile"),
    "cv": ("student", "cv"),
    "cvFit": ("student", "cv"),
    "cvJobFitRail": ("student", "cv"),
    "apply": ("student", "cv"),
    "jobs": ("student", "jobs"),
    "jobInvitations": ("student", "jobs"),
    "applications": ("student", "applications"),
    "messaging": ("student", "messaging"),
    "aiAssistant": ("student", "ai-assistant"),
    "feedback": ("student", "feedback"),
    "rail": ("student", "feedback"),
    # partner
    "team": ("partner", "team"),
    "companyProfile": ("partner", "company-profile"),
    "partnerReviews": ("partner", "partner-reviews"),
    "candidates": ("partner", "candidates"),
    "pipeline": ("partner", "pipeline"),
    "scorecards": ("partner", "scorecards"),
    "interviews": ("partner", "interviews"),
    "offers": ("partner", "offers"),
    "eventsManage": ("partner", "events-manage"),
    "advertising": ("partner", "advertising"),
    "reviews": ("partner", "reviews"),
    "billing": ("partner", "billing"),
    "talentPool": ("partner", "talent-pool"),
    # university
    "partnersReview": ("university", "partners-review"),
    "jobsModeration": ("university", "jobs-moderation"),
    "eventsModeration": ("university", "events-moderation"),
    "moderationHub": ("university", "moderation-hub"),
    "advertisingOversight": ("university", "advertising-oversight"),
    "advertisingCreatives": ("university", "advertising-creatives"),
    "reviewsModeration": ("university", "reviews-moderation"),
    "careerOutcomes": ("university", "career-outcomes"),
    "billingOversight": ("university", "billing-oversight"),
    "aiSettings": ("university", "ai-settings"),
    "universityReports": ("university", "reports"),
    "globalPipeline": ("university", "global-pipeline"),
    "universityUsers": ("university", "users"),
    "analytics": ("university", "analytics"),
    "cvTemplatesAdmin": ("university", "cv-templates-admin"),
    # settings (shared across personas)
    "settings": ("settings", "settings"),
    "notifications": ("settings", "notifications"),
}


def is_dict(v):
    return isinstance(v, dict)


def deep_merge(base, patch):
    result = dict(base)
    for k, v in patch.items():
        if k in result and is_dict(result[k]) and is_dict(v):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    for locale in LOCALES:
        base_path = os.path.join(MSG_DIR, f"{locale}.json")
        tree = load_json(base_path)

        # fold in existing overlay patch files (en/cv.json, en/jobs.json, ...)
        patch_dir = os.path.join(MSG_DIR, locale)
        if os.path.isdir(patch_dir):
            for name in sorted(os.listdir(patch_dir)):
                if not name.endswith(".json"):
                    continue
                patch = load_json(os.path.join(patch_dir, name))
                tree = deep_merge(tree, patch)

        missing = sorted(set(tree.keys()) - set(MAPPING.keys()))
        if missing:
            print(f"ERROR: unmapped namespaces for {locale}: {missing}", file=sys.stderr)
            sys.exit(1)

        # group namespaces -> target file
        buckets = {}
        for ns, value in tree.items():
            group, filename = MAPPING[ns]
            key = (group, filename)
            buckets.setdefault(key, {})[ns] = value

        out_root = os.path.join(MSG_DIR, locale)
        # wipe previous split output (old overlay patch files included) before writing fresh
        if os.path.isdir(out_root):
            for name in os.listdir(out_root):
                p = os.path.join(out_root, name)
                if os.path.isfile(p):
                    os.remove(p)

        for (group, filename), content in buckets.items():
            group_dir = os.path.join(out_root, group)
            os.makedirs(group_dir, exist_ok=True)
            out_path = os.path.join(group_dir, f"{filename}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(content, f, ensure_ascii=False, indent=2, sort_keys=False)
                f.write("\n")

        print(f"{locale}: wrote {len(buckets)} domain files under {out_root}")

    # emit the mapping as a JSON manifest for load.ts generation + parity script
    manifest = {}
    for ns, (group, filename) in MAPPING.items():
        manifest.setdefault(f"{group}/{filename}", []).append(ns)
    with open(os.path.join(MSG_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print("wrote manifest.json")


if __name__ == "__main__":
    main()
