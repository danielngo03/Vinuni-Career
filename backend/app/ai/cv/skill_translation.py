"""Translation-normalization tier for cross-lingual (VN↔EN) CV-JD matching.

The deterministic lexical scorer (``app.ai.cv.job_fit``) only matches a JD skill
term against a CV when the term — or a hand-listed synonym from
``term_expansion.py`` — literally appears in the CV text. A JD asking for
"supply chain management" therefore misses a CV that writes
"quản lý chuỗi cung ứng", and hand-curating every cross-language synonym does not
scale to arbitrary industries.

An embedding tier was tried and REMOVED: on the live ``text-embedding-3-small``
model, true VN↔EN skill pairs scored cosine 0.18–0.59 while same-language
confusables (java/javascript) scored 0.61–0.75 — no threshold separated them
(recall 0). This module replaces it with TRANSLATION-NORMALIZATION: it translates
every skill term to canonical English FIRST (temperature 0, permanently cached),
then lets the existing lexical/ontology tier do the matching. After VN→EN
translation "quản lý chuỗi cung ứng" → "supply chain management" matches the
English form both lexically and exactly.

Design invariants:

- ADD-ONLY / AUGMENTATION. ``english_augment`` appends English forms of the JD
  and CV skill terms; the originals are always kept, so an English CV still
  matches an English JD unchanged. It NEVER removes a term and never mutates its
  inputs in place (shallow copies only).
- GATED. When no real provider is active (offline / default), ``english_augment``
  returns its inputs UNCHANGED, so the downstream ``job_fit.evaluate`` is
  byte-for-byte identical to the pure lexical scorer.
- DETERMINISTIC. Translation runs at temperature 0 and every result is written to
  a permanent cache (DB table ``skill_translation_cache`` + an in-process LRU), so
  the same term always resolves to the same English form.
- CHEAP. English/ASCII terms skip the model entirely (identity). Vietnamese/mixed
  terms are translated ONCE per unique term and cached forever, and translation
  only runs on the fit RECOMPUTE path — a cached fit score never re-translates.
- BEST-EFFORT. Any provider or DB error degrades to an identity map for the
  untranslated terms; this module never raises to its caller.

No provider / model / token / prompt internals ever leave this module.
"""

from __future__ import annotations

import json
import re
import unicodedata

from app.ai.cv import grounding, job_fit
from app.ai.gateway.base import AIMessage
from app.ai.gateway.factory import get_provider_for_alias, real_provider_active
from app.ai.observability.usage import log_ai_usage

# Function-slot handle used for the cheap translation call — a gateway internal;
# no provider/model name is ever exposed to end users.
_TRANSLATE_ALIAS = "chat_default"

# Batch ceiling: how many unique terms we translate in one model call. Kept small
# because a single JD + a handful of CVs rarely exceeds this after ASCII fast-skip.
_MAX_TERMS_PER_CALL = 60

_TRANSLATE_PROMPT = (
    "You normalize job-skill phrases to their STANDARD English skill name as it "
    "appears in real job postings and CVs — NOT a word-for-word translation. For "
    "each numbered input, output the widely-recognized canonical skill term.\n"
    "Rules:\n"
    "- Use the full standard term a recruiter would list (e.g. the LinkedIn/O*NET "
    "form), including its usual words — do not over-shorten.\n"
    "- If the input is already standard English, return it unchanged.\n"
    "- Keep an abbreviation ONLY when it is the common form (SEO, KPI, HR, B2B); "
    "otherwise expand to the full term.\n"
    "- Preserve proper technology/product names exactly (Excel, Kubernetes, Figma, "
    "Photoshop).\n"
    "- Exactly one concise term per input, no explanations, no numbering.\n"
    "Examples:\n"
    '- "an toàn lao động" -> "occupational health and safety"\n'
    '- "chăm sóc khách hàng" -> "customer service"\n'
    '- "quản lý chuỗi cung ứng" -> "supply chain management"\n'
    '- "kế toán tổng hợp" -> "general accounting"\n'
    '- "nhân viên kinh doanh" -> "sales representative"\n'
    '- "kỹ năng đàm phán" -> "negotiation"\n'
    '- "digital marketing" -> "digital marketing"\n'
    "Return ONLY a JSON array of strings, one per input, in the same order, no "
    "extra text."
)

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


# --------------------------------------------------------------------------- #
# Term normalization + diacritic detection                                    #
# --------------------------------------------------------------------------- #

def _norm_key(term: str) -> str:
    """Lowercase + collapse whitespace — the cache key / dedupe key for a term."""
    return grounding.normalize(term)


def _has_vietnamese_diacritics(text: str) -> bool:
    """True when ``text`` contains a non-ASCII letter (Vietnamese diacritic etc.).

    English/ASCII skill names (``python``, ``supply chain management``, ``c++``)
    decompose to pure ASCII and skip the model. Any character carrying a combining
    mark or a codepoint above U+007F (e.g. ``ả``, ``ộ``, ``đ``) marks the term as
    needing translation.
    """
    for ch in unicodedata.normalize("NFD", text):
        if ord(ch) > 0x7F and unicodedata.category(ch).startswith("L"):
            return True
        if unicodedata.combining(ch):
            return True
    return False


# --------------------------------------------------------------------------- #
# In-process LRU (front of the persistent DB cache)                           #
# --------------------------------------------------------------------------- #
# A small manual insertion-ordered dict backs the in-process layer. asyncio is
# single-threaded, so no lock is required.
_LRU: dict[str, str] = {}
_LRU_MAX = 8192


def _lru_lookup(source_norm: str) -> str | None:
    return _LRU.get(source_norm)


def _lru_store(source_norm: str, translated: str) -> None:
    if len(_LRU) >= _LRU_MAX:
        # Drop the oldest ~10% to bound memory without per-item bookkeeping.
        for key in list(_LRU.keys())[: _LRU_MAX // 10]:
            _LRU.pop(key, None)
    _LRU[source_norm] = translated


# --------------------------------------------------------------------------- #
# Persistent DB cache helpers                                                  #
# --------------------------------------------------------------------------- #

async def get_cached_translations(source_norms: list[str]) -> dict[str, str]:
    """Return the cached ``source_norm -> translated`` map for the given keys.

    Best-effort: on any DB error returns ``{}`` so the caller degrades to
    translating (or identity). Opens its own short-lived session — the cache is a
    cross-request shared table, independent of the fit compute transaction.
    """
    if not source_norms:
        return {}
    try:
        from sqlalchemy import select

        from app.core.db import get_sessionmaker
        from app.modules.documents.domain.models import SkillTranslationCache

        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            rows = (
                await session.execute(
                    select(
                        SkillTranslationCache.source_norm,
                        SkillTranslationCache.translated,
                    ).where(SkillTranslationCache.source_norm.in_(source_norms))
                )
            ).all()
        return {str(src): str(tr) for src, tr in rows}
    except Exception:  # noqa: BLE001 - cache is advisory; degrade to translate/identity.
        return {}


async def put_translation(source_norm: str, translated: str) -> None:
    """Persist one ``source_norm -> translated`` mapping (idempotent upsert).

    Best-effort: swallows any DB error so a cache-write failure never breaks the
    fit compute. Commits in its own session so the mapping is durable regardless
    of the caller's transaction outcome.
    """
    if not source_norm or not translated:
        return
    try:
        from sqlalchemy import select

        from app.core.db import get_sessionmaker
        from app.modules.documents.domain.models import SkillTranslationCache

        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            existing = (
                await session.execute(
                    select(SkillTranslationCache).where(
                        SkillTranslationCache.source_norm == source_norm
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    SkillTranslationCache(
                        source_norm=source_norm, translated=translated
                    )
                )
                await session.commit()
    except Exception:  # noqa: BLE001 - cache write is advisory; never raise.
        return


# --------------------------------------------------------------------------- #
# Translation                                                                 #
# --------------------------------------------------------------------------- #

def _parse_translation_array(raw: str, expected: int) -> list[str] | None:
    """Extract a JSON string array from a model response, tolerating junk.

    Returns ``None`` when no well-formed array of the expected length is found so
    the caller falls back to identity for the batch.
    """
    match = _JSON_ARRAY_RE.search(raw or "")
    if match is None:
        return None
    try:
        parsed = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, list) or len(parsed) != expected:
        return None
    out: list[str] = []
    for item in parsed:
        if not isinstance(item, str):
            return None
        out.append(item.strip())
    return out


_TRANSLATE_TASK_TYPE = "skill_translation"


async def _translate_batch(terms: list[str]) -> dict[str, str]:
    """Model-translate a batch of (original) VN/mixed terms → English.

    Returns ``{original_term: english_term}`` for the terms that translated
    cleanly; on any error returns ``{}`` so the caller maps them to identity.

    Every model call (success AND failure) is recorded to ``ai_usage_log`` via
    ``log_ai_usage`` so translation cost is tracked like every other gateway call
    (AI rules §5.4), without exposing provider/model/token internals.
    """
    if not terms:
        return {}
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(terms))
    content = f"{_TRANSLATE_PROMPT}\n\n{numbered}"
    try:
        provider = get_provider_for_alias(_TRANSLATE_ALIAS)
        completion = await provider.complete(
            messages=[AIMessage(role="user", content=content)],
            alias=_TRANSLATE_ALIAS,
            temperature=0.0,
            max_tokens=1000,
        )
    except Exception:  # noqa: BLE001 - translation is advisory; degrade to identity.
        log_ai_usage(task_type=_TRANSLATE_TASK_TYPE, alias=_TRANSLATE_ALIAS, success=False)
        return {}

    parsed = _parse_translation_array(completion.text, expected=len(terms))
    if parsed is None:
        # Model responded but the output was unusable — still a real (billable) call.
        log_ai_usage(
            task_type=_TRANSLATE_TASK_TYPE, alias=_TRANSLATE_ALIAS, success=False,
            prompt_chars=len(content), completion_chars=len(completion.text or ""),
        )
        return {}
    log_ai_usage(
        task_type=_TRANSLATE_TASK_TYPE, alias=_TRANSLATE_ALIAS, success=True,
        prompt_chars=len(content), completion_chars=len(completion.text or ""),
    )
    out: dict[str, str] = {}
    for original, english in zip(terms, parsed, strict=True):
        english = english.strip()
        if english:
            out[original] = english
    return out


async def normalize_terms_to_en(
    terms: list[str], *, allow_model_calls: bool = True
) -> dict[str, str]:
    """Map each unique non-empty ``term`` → its canonical English skill term.

    - FAST-SKIP: a term with NO Vietnamese diacritics that is already ASCII/English
      maps to itself with NO model call.
    - The remaining (Vietnamese / mixed) terms are resolved against the in-process
      LRU, then the persistent DB cache, then — for the misses — batch-translated
      through the chat gateway at temperature 0. Results are written back to both
      cache layers so the same term is translated at most once, ever.
    - GATED + BEST-EFFORT: when no real provider is active, or on any error, the
      untranslated terms map to themselves (identity). Never raises.
    - ``allow_model_calls=False`` runs CACHE-ONLY: LRU + DB hits are still used
      (already-warm terms translate for free), but cache MISSES are NOT sent to the
      model — they map to identity. This keeps high-volume request paths (job list,
      batch card scoring) fast and non-blocking: a real model call per term × dozens
      of jobs would otherwise stall the request for tens of seconds. The single-job
      detail path uses the default (model calls allowed) to warm the cache.

    The returned dict is keyed by the ORIGINAL term string (first spelling seen for
    a given normalized key) so the caller can look up its own term values directly.
    """
    # De-duplicate on normalized key, keeping the first original spelling.
    originals_by_key: dict[str, str] = {}
    for term in terms:
        if not isinstance(term, str):
            continue
        stripped = term.strip()
        if not stripped:
            continue
        key = _norm_key(stripped)
        if key and key not in originals_by_key:
            originals_by_key[key] = stripped

    result: dict[str, str] = {}
    to_resolve_keys: list[str] = []  # normalized keys still needing translation
    for key, original in originals_by_key.items():
        if not _has_vietnamese_diacritics(original):
            result[original] = original  # ASCII/English → identity, no model.
        else:
            to_resolve_keys.append(key)

    if not to_resolve_keys:
        return result

    # LRU layer.
    still_missing: list[str] = []
    for key in to_resolve_keys:
        cached = _lru_lookup(key)
        if cached is not None:
            result[originals_by_key[key]] = cached
        else:
            still_missing.append(key)

    # Persistent DB layer. Skipped in cache-only mode: a per-job DB round-trip on
    # the discovery list / batch card path (dozens of jobs, each with JD + CV-prose
    # lookups) adds up to many seconds. Cache-only relies on the in-process LRU,
    # which the single-job detail path warms with real translations.
    if still_missing and allow_model_calls:
        db_hits = await get_cached_translations(still_missing)
        remaining: list[str] = []
        for key in still_missing:
            if key in db_hits:
                translated = db_hits[key]
                _lru_store(key, translated)
                result[originals_by_key[key]] = translated
            else:
                remaining.append(key)
        still_missing = remaining

    # If AI is off, cache-only mode, or nothing left, identity-fill and return.
    if not still_missing:
        return result
    if not allow_model_calls or not real_provider_active():
        for key in still_missing:
            result[originals_by_key[key]] = originals_by_key[key]
        return result

    # Model layer — translate the misses in bounded batches (originals, not keys,
    # so the model sees the natural phrase; the cache is keyed by the norm key).
    miss_originals = [originals_by_key[key] for key in still_missing]
    translated_map: dict[str, str] = {}
    for start in range(0, len(miss_originals), _MAX_TERMS_PER_CALL):
        batch = miss_originals[start : start + _MAX_TERMS_PER_CALL]
        translated_map.update(await _translate_batch(batch))

    for key in still_missing:
        original = originals_by_key[key]
        english = translated_map.get(original)
        # A non-empty result that STILL carries Vietnamese diacritics for a
        # Vietnamese input is a model echo / non-translation, not a real English
        # form. Treat it as a failure: map to identity for THIS request and DO
        # NOT persist it, so a later request retries the model instead of being
        # served a poisoned cache row forever. This mirrors the diacritic guard
        # ``english_augment`` uses for its ``complete`` flag and the fit-score
        # store's ``~provisional`` retry contract. (An empty result was already a
        # failure.) A genuine translation — or an ASCII/English echo, which is a
        # valid identity — is still cached exactly as before.
        poisoned = bool(
            english
            and _has_vietnamese_diacritics(original)
            and _has_vietnamese_diacritics(english)
        )
        if english and not poisoned:
            _lru_store(key, english)
            await put_translation(key, english)
            result[original] = english
        else:
            result[original] = original  # empty or untranslated echo → identity, not cached.
    return result


# --------------------------------------------------------------------------- #
# English augmentation of JD + CV inputs                                       #
# --------------------------------------------------------------------------- #

def _cv_skill_item_names(cv: job_fit.CvInput) -> list[str]:
    """Collect one CV's skill-section item names/text (for translation)."""
    names: list[str] = []
    for section in cv.sections:
        stype = grounding.normalize(str(section.get("section_type") or ""))
        if "skill" not in stype:
            continue
        content = section.get("content") or section.get("content_json")
        if not isinstance(content, dict):
            continue
        items = content.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, str) and item.strip():
                names.append(item.strip())
            elif isinstance(item, dict):
                value = item.get("name") or item.get("text")
                if isinstance(value, str) and value.strip():
                    names.append(value.strip())
    return names


# CV section types whose free-form prose (experience / education / summary /
# projects) is translated to English on the VN→EN path so the ROLE / EXPERIENCE /
# CREDENTIALS bands can match an English JD. Skill sections are handled separately
# via ``skills_en`` and are excluded here.
_PROSE_SECTION_TYPES = frozenset(
    {
        "experience",
        "work",
        "work_experience",
        "education",
        "summary",
        "objective",
        "projects",
        "project",
        "internship",
    }
)

# Ceiling on the CV prose we translate in one cached unit. One JD detail view
# scores a handful of CVs; capping bounds the single translation call's cost while
# still covering the substantive experience/education evidence.
_MAX_PROSE_CHARS = 2500


def _cv_prose_text(cv: job_fit.CvInput) -> str:
    """Collect one CV's experience/education/summary/projects prose (capped).

    Returns the concatenated, whitespace-normalized text of the CV's prose
    sections, truncated to ``_MAX_PROSE_CHARS``. Empty string when the CV has no
    such sections.
    """
    parts: list[str] = []
    for section in cv.sections:
        stype = grounding.normalize(str(section.get("section_type") or "")).replace(
            " ", "_"
        )
        if stype not in _PROSE_SECTION_TYPES:
            continue
        text = grounding.content_to_text(
            section.get("content") or section.get("content_json")
        )
        if text.strip():
            parts.append(text.strip())
    collected = " ".join(parts).strip()
    if len(collected) > _MAX_PROSE_CHARS:
        collected = collected[:_MAX_PROSE_CHARS]
    return collected


async def _translate_prose_unit(text: str, *, allow_model_calls: bool = True) -> str | None:
    """Translate one capped CV-prose blob to English as a SINGLE cached unit.

    Reuses ``normalize_terms_to_en`` (its LRU + DB cache + batch model call keyed
    on the normalized content), so repeated CV versions carrying the same prose do
    not re-translate. Best-effort: returns ``None`` when translation is unavailable
    or yields no change, so the caller simply skips the ``translated_en`` section.
    ``allow_model_calls=False`` is cache-only (see ``normalize_terms_to_en``).
    """
    if not text.strip():
        return None
    mapping = await normalize_terms_to_en([text], allow_model_calls=allow_model_calls)
    english = mapping.get(text)
    if not english:
        return None
    if _norm_key(english) == _norm_key(text):
        return None
    return english


def _jd_skill_terms(job: dict) -> list[str]:
    """The curated JD skill strings eligible for English augmentation."""
    out: list[str] = []
    for key in ("required_skills", "preferred_skills"):
        group = job.get(key)
        if isinstance(group, list):
            out.extend(v for v in group if isinstance(v, str) and v.strip())
    return out


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = _norm_key(value)
        if key and key not in seen:
            seen.add(key)
            out.append(value)
    return out


async def english_augment(
    job: dict, cv_inputs: list[job_fit.CvInput], *, allow_model_calls: bool = True
) -> tuple[dict, list[job_fit.CvInput], bool]:
    """Append canonical-English forms of JD + CV skill terms for lexical matching.

    Returns ``(job2, cv_inputs2, complete)`` where:

    - ``job2`` is a SHALLOW copy of ``job`` whose ``required_skills`` /
      ``preferred_skills`` are the originals PLUS their English translations
      (deduped; originals kept so English CVs still match).
    - each CV in ``cv_inputs2`` is a copy that gains ONE extra synthetic
      ``skills_en`` section listing the English forms of its skill items, so the
      lexical matcher's CV text now contains the English skill forms. Originals are
      untouched.

    ``complete`` is ``True`` when the augmentation is trustworthy to CACHE: either
    AI is off (offline lexical is the intended result, not a degradation) or every
    Vietnamese term/prose we attempted translated successfully. It is ``False``
    when AI IS on but a translation call FAILED (provider down / timeout /
    malformed) so some Vietnamese evidence fell back to identity — the caller
    should then serve the (degraded lexical) score for THIS request but NOT persist
    it as a fresh store row, so the next request retries once AI recovers.

    Gated: when no real provider is active, returns ``(job, cv_inputs, True)``
    UNCHANGED (offline is pure lexical, byte-identical). Never mutates inputs.
    """
    if not real_provider_active():
        return job, cv_inputs, True

    # One deduped translation set for the whole job + all CVs (batched, cached).
    jd_terms = _jd_skill_terms(job)
    cv_terms_by_id: dict[str, list[str]] = {
        cv.cv_id: _cv_skill_item_names(cv) for cv in cv_inputs
    }
    all_terms: list[str] = [*jd_terms]
    for terms in cv_terms_by_id.values():
        all_terms.extend(terms)
    # Prose translation (below) can still add value for a Vietnamese CV that lists
    # no structured skill items, so only bail early when there is NOTHING to
    # translate on either the skills OR the prose side.
    has_prose = any(_cv_prose_text(cv).strip() for cv in cv_inputs)
    if not all_terms and not has_prose:
        return job, cv_inputs, True

    translations = (
        await normalize_terms_to_en(
            _dedupe_keep_order(all_terms), allow_model_calls=allow_model_calls
        )
        if all_terms
        else {}
    )

    # Degradation signal: a Vietnamese term that comes back still carrying Vietnamese
    # diacritics means its translation call FAILED (``normalize_terms_to_en`` identity-
    # fills on failure). Any such failure marks the augmentation incomplete so the
    # caller does not cache a degraded score.
    complete = True
    for term in all_terms:
        if _has_vietnamese_diacritics(term) and _has_vietnamese_diacritics(
            translations.get(term, term)
        ):
            complete = False
            break

    def _english_of(term: str) -> str | None:
        english = translations.get(term)
        if english and _norm_key(english) != _norm_key(term):
            return english
        return None

    # --- Augment the JD (shallow copy; originals kept, English appended). ---
    # ``translation_map`` folds each surfaced (original, translation) pair back to
    # ONE user-facing entry downstream: both the original's norm-key and the English
    # translation's norm-key map to the ORIGINAL display spelling, so ``job_fit``
    # never shows a Vietnamese skill and its English translation as two separate
    # matched/gap entries. Keyed off the original JD skills only (never CV terms).
    job2 = dict(job)
    translation_map: dict[str, str] = {}
    for key in ("required_skills", "preferred_skills"):
        group = job.get(key)
        if not isinstance(group, list):
            continue
        augmented = list(group)
        for value in group:
            if isinstance(value, str):
                english = _english_of(value)
                if english is not None:
                    augmented.append(english)
                    original = value.strip()
                    translation_map[_norm_key(original)] = original
                    translation_map[_norm_key(english)] = original
        job2[key] = _dedupe_keep_order(
            [v for v in augmented if isinstance(v, str) and v.strip()]
        )
    if translation_map:
        # Internal surfacing hint consumed by ``job_fit.resolve_requirements``;
        # never surfaced to end users (stripped by the response presenter, which
        # only reads score/bands/matched/gaps).
        job2["_skill_translation_map"] = translation_map

    # --- Augment each CV with synthetic English sections. ---
    # Two synthetic sections may be appended per CV:
    #   * ``skills_en``     — English forms of the CV's skill items (feeds SKILLS +
    #                         ROLE + EXPERIENCE bands).
    #   * ``translated_en`` — English translation of the CV's experience / education
    #                         / summary / projects prose (feeds ROLE + EXPERIENCE +
    #                         CREDENTIALS). Only produced for Vietnamese/mixed CVs
    #                         (diacritic-gated), capped, and translated as ONE cached
    #                         unit so English CVs and repeated versions cost nothing.
    cv_inputs2: list[job_fit.CvInput] = []
    for cv in cv_inputs:
        extra_sections: list[dict] = []

        english_names = _dedupe_keep_order(
            [
                english
                for name in cv_terms_by_id[cv.cv_id]
                if (english := _english_of(name)) is not None
            ]
        )
        if english_names:
            extra_sections.append(
                {
                    "section_type": "skills_en",
                    "title": "Skills (EN)",
                    "content": {"items": [{"text": name} for name in english_names]},
                }
            )

        prose = _cv_prose_text(cv)
        if prose and _has_vietnamese_diacritics(prose):
            english_prose = await _translate_prose_unit(
                prose, allow_model_calls=allow_model_calls
            )
            if english_prose:
                extra_sections.append(
                    {
                        "section_type": "translated_en",
                        "title": "Translated (EN)",
                        "content": {"items": [{"text": english_prose}]},
                    }
                )
            else:
                # VN prose that did not translate → a failed call; don't cache.
                complete = False

        if not extra_sections:
            cv_inputs2.append(cv)
            continue
        cv_inputs2.append(
            job_fit.CvInput(
                cv_id=cv.cv_id,
                title=cv.title,
                language=cv.language,
                sections=[*cv.sections, *extra_sections],
                last_updated_days=cv.last_updated_days,
            )
        )

    # Cache-only mode never made a model call, so an untranslated term is the
    # INTENDED result (not a degraded failure) — the score is safe to cache as
    # fresh. ``complete`` only signals "AI was allowed to translate but a call
    # failed", which cannot happen when model calls are disabled.
    if not allow_model_calls:
        complete = True

    return job2, cv_inputs2, complete
