#!/usr/bin/env node
/**
 * Locale message parity gate.
 *
 * Every translation file under src/messages/{locale}/... must exist for both
 * `en` and `vi`, and every key path inside a file must exist (with a
 * non-empty string leaf) in the matching file for the other locale. This
 * catches: a namespace added in one locale only, a key added/renamed in one
 * locale only, and empty/placeholder strings left behind during translation.
 *
 * Usage: node scripts/check-message-parity.mjs
 * Exit code 0 = in sync, 1 = drift found (prints a report).
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const MESSAGES_DIR = join(__dirname, "..", "src", "messages");
const LOCALES = ["en", "vi"];

function listJsonFiles(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const s = statSync(full);
    if (s.isDirectory()) {
      out.push(...listJsonFiles(full));
    } else if (entry.endsWith(".json")) {
      out.push(full);
    }
  }
  return out;
}

function relPath(locale, absPath) {
  return relative(join(MESSAGES_DIR, locale), absPath);
}

function flattenKeys(obj, prefix = "") {
  const keys = [];
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) {
      keys.push(...flattenKeys(v, path));
    } else {
      keys.push([path, v]);
    }
  }
  return keys;
}

function main() {
  const filesByLocale = {};
  for (const locale of LOCALES) {
    const dir = join(MESSAGES_DIR, locale);
    filesByLocale[locale] = new Map(
      listJsonFiles(dir).map((f) => [relPath(locale, f), f]),
    );
  }

  const problems = [];

  const allRelPaths = new Set([
    ...filesByLocale.en.keys(),
    ...filesByLocale.vi.keys(),
  ]);

  for (const rel of [...allRelPaths].sort()) {
    const enFile = filesByLocale.en.get(rel);
    const viFile = filesByLocale.vi.get(rel);

    if (!enFile) {
      problems.push(`Missing en file: src/messages/en/${rel}`);
      continue;
    }
    if (!viFile) {
      problems.push(`Missing vi file: src/messages/vi/${rel}`);
      continue;
    }

    const enJson = JSON.parse(readFileSync(enFile, "utf-8"));
    const viJson = JSON.parse(readFileSync(viFile, "utf-8"));
    const enKeys = new Map(flattenKeys(enJson));
    const viKeys = new Map(flattenKeys(viJson));

    for (const key of enKeys.keys()) {
      if (!viKeys.has(key)) {
        problems.push(`${rel}: key "${key}" exists in en but missing in vi`);
      }
    }
    for (const key of viKeys.keys()) {
      if (!enKeys.has(key)) {
        problems.push(`${rel}: key "${key}" exists in vi but missing in en`);
      }
    }
    for (const [key, value] of enKeys) {
      if (typeof value === "string" && value.trim() === "") {
        problems.push(`${rel}: en key "${key}" is an empty string`);
      }
    }
    for (const [key, value] of viKeys) {
      if (typeof value === "string" && value.trim() === "") {
        problems.push(`${rel}: vi key "${key}" is an empty string`);
      }
    }
  }

  if (problems.length > 0) {
    console.error(`Locale parity check failed — ${problems.length} issue(s):\n`);
    for (const p of problems) console.error(`  - ${p}`);
    console.error(
      "\nFix: add/remove the matching key in the other locale file, or fill in the empty string.",
    );
    process.exit(1);
  }

  console.log(
    `Locale parity OK — ${allRelPaths.size} file(s) checked across ${LOCALES.join("/")}.`,
  );
}

main();
