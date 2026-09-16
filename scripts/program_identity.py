#!/usr/bin/env python3
"""Deterministic programme identity, genealogy and review-priority utilities.

This module intentionally avoids opaque embeddings. Every match and score is
explainable from identifiers, curated aliases, source class and explicit
research signals.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "monitor" / "program_registry.json"

STOPWORDS = {
    "a", "an", "and", "for", "in", "of", "on", "the", "to", "with", "from",
    "multiple", "sclerosis", "ms", "study", "trial", "therapy", "treatment",
    "remyelination", "remyelinating", "myelin", "repair", "regeneration",
}


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def load_registry(path: Path = REGISTRY_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _alias_specific(alias: str) -> bool:
    raw = (alias or "").strip()
    n = normalize(raw)
    if not n:
        return False
    if " " in n:
        return len(n) >= 7
    if any(ch.isdigit() for ch in raw):
        return len(n) >= 4
    if raw.isupper():
        return len(n) >= 5
    return len(n) >= 7


def _contains_alias(haystack: str, alias: str) -> bool:
    a = normalize(alias)
    h = f" {normalize(haystack)} "
    return bool(a and f" {a} " in h)


def build_indexes(registry: dict) -> tuple[dict[str, dict], list[tuple[str, dict]]]:
    identifier_index: dict[str, dict] = {}
    aliases: list[tuple[str, dict]] = []
    for programme in registry.get("programs", []):
        for identifier in programme.get("identifiers", []):
            key = str(identifier).strip().upper()
            if key:
                identifier_index[key] = programme
        for alias in programme.get("aliases", []):
            if _alias_specific(alias):
                aliases.append((alias, programme))
    aliases.sort(key=lambda item: len(normalize(item[0])), reverse=True)
    return identifier_index, aliases


def match_programme(candidate: dict, registry: dict | None = None) -> dict:
    registry = registry or load_registry()
    identifier_index, aliases = build_indexes(registry)
    stable_id = str(candidate.get("id") or "").strip()
    stable_upper = stable_id.upper()
    title = str(candidate.get("title") or "")
    meta = json.dumps(candidate.get("meta") or {}, ensure_ascii=False)
    haystack = " ".join([stable_id, title, str(candidate.get("url") or ""), meta])

    programme = identifier_index.get(stable_upper)
    if programme:
        return _match_payload(programme, "identifier", stable_id, 100, "known_record")

    # Also recognise known identifiers embedded in title/metadata.
    upper_haystack = haystack.upper()
    for identifier, programme in identifier_index.items():
        if identifier and identifier in upper_haystack:
            return _match_payload(programme, "embedded_identifier", identifier, 98, "known_program_mention")

    for alias, programme in aliases:
        if _contains_alias(haystack, alias):
            source = str(candidate.get("source") or "").lower()
            is_registry = any(x in source for x in ("clinicaltrials", "ctis", "anzctr", "isrctn"))
            status = "known_program_new_record" if is_registry and stable_id else "known_program_mention"
            return _match_payload(programme, "alias", alias, 88, status)

    return {
        "canonical_program_id": None,
        "canonical_program_name": None,
        "identity_method": "none",
        "identity_evidence": None,
        "identity_confidence": 0,
        "identity_status": "unmatched",
        "family_id": None,
        "relations": [],
        "entity_type": None,
    }


def _match_payload(programme: dict, method: str, evidence: str, confidence: int, status: str) -> dict:
    return {
        "canonical_program_id": programme.get("canonical_id"),
        "canonical_program_name": programme.get("canonical_name"),
        "identity_method": method,
        "identity_evidence": evidence,
        "identity_confidence": confidence,
        "identity_status": status,
        "family_id": programme.get("family_id"),
        "relations": programme.get("relations") or [],
        "entity_type": programme.get("entity_type"),
    }


def source_class(source: str, source_quality: str = "") -> tuple[str, int]:
    text = f"{source} {source_quality}".lower()
    if any(x in text for x in ("clinicaltrials.gov", "eu ctis", "anzctr", "isrctn", "primary trial registry", "human trial registry")):
        return "primary_registry", 92
    if "europe pmc" in text and "preprint" not in text:
        return "peer_reviewed_index", 76
    if any(x in text for x in ("biorxiv", "medrxiv", "preprint")):
        return "preprint", 52
    if any(x in text for x in ("nih reporter", "ukri", "cordis", "grant", "official public grant", "eu project")):
        return "official_funding_or_project", 72
    if any(x in text for x in ("ectrims", "actrims", "conference")):
        return "official_conference", 66
    if "news discovery" in text or "secondary discovery" in text:
        return "secondary_news", 34
    if any(x in text for x in ("company", "university", "official", "tech-transfer", "tech transfer", "investigator")):
        return "official_programme_page", 70
    return "other", 55


def review_confidence(candidate: dict) -> dict:
    cls, score = source_class(str(candidate.get("source") or ""), str(candidate.get("source_quality") or ""))
    reasons = [f"source:{cls}={score}"]

    if candidate.get("human_data"):
        score += 6
        reasons.append("human-study-context:+6")
    if candidate.get("greece_priority"):
        score += 7
        reasons.append("greece-priority:+7")
    if candidate.get("repair_hits"):
        score += 5
        reasons.append("explicit-repair-signal:+5")
    if candidate.get("translation_hits"):
        score += 4
        reasons.append("development-signal:+4")
    if candidate.get("model_hits") and not candidate.get("human_data"):
        score -= 6
        reasons.append("preclinical-model-only:-6")
    if cls == "preprint":
        score -= 4
        reasons.append("not-peer-reviewed:-4")
    if cls == "secondary_news":
        score -= 4
        reasons.append("secondary-source:-4")

    score = max(0, min(100, int(score)))
    if score >= 88:
        band = "very_high"
    elif score >= 72:
        band = "high"
    elif score >= 55:
        band = "moderate"
    else:
        band = "low"
    return {
        "review_confidence": score,
        "review_confidence_band": band,
        "source_class": cls,
        "review_confidence_reasons": reasons,
    }


def title_tokens(title: str) -> set[str]:
    return {
        token for token in normalize(title).split()
        if len(token) >= 4 and token not in STOPWORDS
    }


def title_similarity(a: str, b: str) -> float:
    ta, tb = title_tokens(a), title_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def validate_registry(registry: dict | None = None) -> list[str]:
    registry = registry or load_registry()
    errors: list[str] = []
    canonical_ids: set[str] = set()
    identifiers: dict[str, str] = {}
    aliases: dict[str, str] = {}
    for p in registry.get("programs", []):
        cid = str(p.get("canonical_id") or "").strip()
        if not cid:
            errors.append("programme missing canonical_id")
            continue
        if cid in canonical_ids:
            errors.append(f"duplicate canonical_id: {cid}")
        canonical_ids.add(cid)
        if not p.get("canonical_name"):
            errors.append(f"{cid}: missing canonical_name")
        for identifier in p.get("identifiers", []):
            key = str(identifier).upper()
            previous = identifiers.get(key)
            if previous and previous != cid:
                errors.append(f"identifier {identifier} assigned to both {previous} and {cid}")
            identifiers[key] = cid
        for alias in p.get("aliases", []):
            if not _alias_specific(alias):
                continue
            key = normalize(alias)
            previous = aliases.get(key)
            if previous and previous != cid:
                errors.append(f"alias {alias!r} assigned to both {previous} and {cid}")
            aliases[key] = cid
        for relation in p.get("relations", []):
            target = relation.get("target")
            if target and target == cid:
                errors.append(f"{cid}: self-referential relation")
    return errors
