#!/usr/bin/env python3
"""Weekly broad discovery for MS remyelination / myelin-repair research.

Discovers new candidate programmes outside the known watchlist. It never edits
news.json or publishes clinical conclusions. First run establishes a baseline;
later runs emit only newly seen high-signal candidates.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

from program_identity import load_registry, match_programme

ROOT = Path(__file__).resolve().parents[1]
MON = ROOT / "monitor"
CONFIG = json.loads((MON / "discovery_config.json").read_text(encoding="utf-8"))
WATCH = json.loads((MON / "watchlist.json").read_text(encoding="utf-8"))
PROGRAM_REGISTRY = load_registry()
STATE_PATH = MON / "discovery_state.json"
REPORT_PATH = MON / "discovery_report.json"
UA = "MSNewsFetch-deep-discovery/1.0 (+https://github.com/fokas-hoa/msnewsfetch)"

NCT_RE = re.compile(r"\bNCT\d{8}\b", re.I)
CTIS_RE = re.compile(r"\b20\d{2}-\d{6}-\d{2}-\d{2}\b")
ACTRN_RE = re.compile(r"\bACTRN\d{14}[A-Za-z]?\b", re.I)


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.links = []
        self._href = None
        self._anchor_parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._anchor_parts = []

    def handle_data(self, data):
        text = " ".join(data.split())
        if text:
            self.parts.append(text)
            if self._href is not None:
                self._anchor_parts.append(text)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._anchor_parts).strip()))
            self._href = None
            self._anchor_parts = []

    def text(self):
        return " ".join(self.parts)


def req(url, *, data=None, headers=None, timeout=45):
    h = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        h.update(headers)
    request = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def get_json(url):
    return json.loads(req(url, headers={"Accept": "application/json"}).decode("utf-8"))


def post_json(url, payload):
    raw = json.dumps(payload).encode("utf-8")
    return json.loads(req(url, data=raw, headers={"Accept": "application/json", "Content-Type": "application/json"}).decode("utf-8"))


def html_text(raw):
    p = TextParser()
    p.feed(raw.decode("utf-8", "replace"))
    return re.sub(r"\s+", " ", unescape(p.text())).strip(), p.links


def norm(s):
    return re.sub(r"[^a-z0-9α-ω]+", " ", (s or "").lower()).strip()


def contains_any(text, terms):
    low = text.lower()
    return sorted({term for term in terms if term.lower() in low})


def known_context():
    ids = set()
    aliases = []
    for x in WATCH.get("clinicaltrials", []):
        if x.get("id"):
            ids.add(x["id"].upper())
        if x.get("name"):
            aliases.append(x["name"])
    for x in WATCH.get("ctis", []):
        if x.get("id"):
            ids.add(x["id"])
        if x.get("name"):
            aliases.append(x["name"])
    aliases.extend(WATCH.get("program_aliases", []))

    news = ROOT / "news.json"
    if news.exists():
        try:
            data = json.loads(news.read_text(encoding="utf-8"))
            for section in ("pipeline", "translational", "readouts", "items", "greece"):
                for item in data.get(section, []):
                    for field in ("name", "title", "candidate"):
                        if item.get(field):
                            aliases.append(str(item[field]))
                    dumped = json.dumps(item)
                    for match in NCT_RE.findall(dumped):
                        ids.add(match.upper())
                    for match in CTIS_RE.findall(dumped):
                        ids.add(match)
        except Exception:
            pass
    aliases = [alias for alias in aliases if len(norm(alias)) >= 8]
    return ids, aliases


KNOWN_IDS, KNOWN_ALIASES = known_context()


def is_known(stable_id, text):
    if stable_id.upper() in KNOWN_IDS or stable_id in KNOWN_IDS:
        return True
    nt = norm(text)
    for alias in KNOWN_ALIASES:
        na = norm(alias)
        if len(na) >= 8 and na in nt:
            return True
    return False


def classify(text, *, human=False, greece=False, grant=False, preprint=False):
    strong = contains_any(text, CONFIG["strong_repair_terms"])
    linked = contains_any(text, CONFIG["linked_terms"])
    ms = contains_any(text, CONFIG["ms_terms"])
    trans = contains_any(text, CONFIG["translation_terms"])
    model = contains_any(text, CONFIG["model_terms"])

    score = 0
    if ms:
        score += 2
    if strong:
        score += 4
    elif linked:
        score += 2
    if trans:
        score += 2
    if human:
        score += 3
    if grant:
        score += 1
    if greece:
        score += 2
    if model and not human and not trans:
        score -= 2

    eligible = bool(ms and (strong or linked))
    if eligible and model and not (trans or human or grant):
        eligible = False
    return {
        "score": score,
        "eligible": eligible,
        "strong_hits": strong[:8],
        "linked_hits": linked[:8],
        "translation_hits": trans[:8],
        "model_hits": model[:8],
        "human": human,
        "greece": greece,
        "grant": grant,
        "preprint": preprint,
    }


def load_state():
    if not STATE_PATH.exists():
        return {"version": 1, "seen": {}}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "seen": {}}


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def candidate(source, stable_id, title, url, text, meta, *, evidence, source_quality):
    c = classify(
        text,
        human=bool(meta.get("human")),
        greece=bool(meta.get("greece")),
        grant=bool(meta.get("grant")),
        preprint=bool(meta.get("preprint")),
    )
    if not c["eligible"] or c["score"] < 5:
        return None
    identity_probe = {
        "source": source,
        "id": stable_id,
        "title": title,
        "url": url,
        "meta": meta,
    }
    identity = match_programme(identity_probe, PROGRAM_REGISTRY)

    # Do not discard a genuinely new registry record merely because its title
    # contains a known programme alias. Exact known records and ordinary known
    # programme mentions are still suppressed here; novel registry IDs survive
    # to become known_program_new_record during identity enrichment.
    if is_known(stable_id, f"{title} {text}") and identity.get("identity_status") != "known_program_new_record":
        return None
    return {
        **identity,
        "source": source,
        "id": stable_id,
        "title": title.strip()[:300],
        "url": url,
        "evidence": evidence,
        "source_quality": source_quality,
        "score": c["score"],
        "greece_priority": c["greece"],
        "human_data": c["human"],
        "repair_hits": c["strong_hits"] or c["linked_hits"],
        "translation_hits": c["translation_hits"],
        "model_hits": c["model_hits"],
        "clinical_note": (
            "Human trial/programme candidate; registration or human testing does not prove clinical benefit."
            if c["human"] else
            "Preclinical/translational candidate only; no proven clinical benefit in people."
        ),
        "meta": {k: v for k, v in meta.items() if k not in {"human", "greece", "grant", "preprint"}},
    }


def scan_clinicaltrials(warnings):
    out, seen = [], set()
    for query in CONFIG["clinicaltrials_queries"]:
        try:
            params = urllib.parse.urlencode({"query.term": query, "pageSize": 100, "format": "json"})
            data = get_json("https://clinicaltrials.gov/api/v2/studies?" + params)
            for study in data.get("studies", []):
                p = study.get("protocolSection", {})
                ident = p.get("identificationModule", {})
                stat = p.get("statusModule", {})
                cond = p.get("conditionsModule", {})
                desc = p.get("descriptionModule", {})
                arms = p.get("armsInterventionsModule", {})
                contacts = p.get("contactsLocationsModule", {})
                design = p.get("designModule", {})
                nct = (ident.get("nctId") or "").upper()
                if not nct or nct in seen:
                    continue
                seen.add(nct)
                title = ident.get("briefTitle") or ident.get("officialTitle") or nct
                interventions = arms.get("interventions") or []
                locations = contacts.get("locations") or []
                countries = sorted({x.get("country") for x in locations if x.get("country")})
                text = " ".join([
                    title,
                    ident.get("officialTitle") or "",
                    " ".join(cond.get("conditions") or []),
                    " ".join(cond.get("keywords") or []),
                    desc.get("briefSummary") or "",
                    " ".join((x.get("name") or "") + " " + (x.get("description") or "") for x in interventions),
                ])
                c = candidate(
                    "ClinicalTrials.gov", nct, title, f"https://clinicaltrials.gov/study/{nct}", text,
                    {
                        "human": True,
                        "greece": "Greece" in countries,
                        "status": stat.get("overallStatus"),
                        "phases": design.get("phases") or [],
                        "countries": countries,
                    },
                    evidence="Human trial registration",
                    source_quality="Primary trial registry",
                )
                if c:
                    out.append(c)
        except Exception as e:
            warnings.append(f"ClinicalTrials.gov query failed: {query!r} ({type(e).__name__})")
    return out


def scan_europepmc(warnings):
    out, seen = [], set()
    for query0 in CONFIG["europepmc_queries"]:
        try:
            params = urllib.parse.urlencode({
                "query": f"({query0}) sort_date:y",
                "format": "json",
                "resultType": "core",
                "pageSize": 100,
            })
            data = get_json("https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + params)
            for result in (data.get("resultList") or {}).get("result", []):
                rid = str(result.get("doi") or result.get("pmid") or result.get("pmcid") or result.get("id") or "")
                if not rid or rid in seen:
                    continue
                seen.add(rid)
                title = result.get("title") or rid
                abstract = result.get("abstractText") or ""
                pubtypes = result.get("pubTypeList", {}).get("pubType", []) if isinstance(result.get("pubTypeList"), dict) else []
                text = " ".join([title, abstract, " ".join(pubtypes or [])])
                is_preprint = result.get("source") == "PPR" or any("preprint" in x.lower() for x in (pubtypes or []))
                human = any(x in text.lower() for x in ("clinical trial", "randomized", "randomised", "patient", "participants"))
                article_id = result.get("id") or result.get("pmid") or rid
                url = f"https://europepmc.org/article/{result.get('source', 'MED')}/{urllib.parse.quote(str(article_id))}"
                c = candidate(
                    "Europe PMC", rid, title, url, text,
                    {"human": human, "preprint": is_preprint, "journal": result.get("journalTitle"), "pub_date": result.get("firstPublicationDate")},
                    evidence="Preprint" if is_preprint else "Peer-reviewed/biomedical publication index",
                    source_quality="Preprint index — requires peer-review caution" if is_preprint else "Europe PMC bibliographic record",
                )
                if c:
                    out.append(c)
        except Exception as e:
            warnings.append(f"Europe PMC query failed: {query0!r} ({type(e).__name__})")
    return out


def scan_preprints(warnings):
    out, seen = [], set()
    end = date.today()
    start = end - timedelta(days=int(CONFIG.get("lookback_days", 45)))
    cats = CONFIG.get("preprint_categories", {"biorxiv": ["neuroscience"], "medrxiv": ["neurology"]})
    for server, categories in cats.items():
        for category in categories:
            cursor, fetched = 0, 0
            while fetched < 360:
                try:
                    cat = urllib.parse.quote(category, safe="")
                    url = f"https://api.biorxiv.org/details/{server}/{start.isoformat()}/{end.isoformat()}/{cursor}?category={cat}"
                    data = get_json(url)
                    collection = data.get("collection") or []
                    if not collection:
                        break
                    for result in collection:
                        rid = str(result.get("doi") or "")
                        if not rid or rid in seen:
                            continue
                        seen.add(rid)
                        title = result.get("title") or rid
                        text = " ".join([title, result.get("abstract") or "", result.get("category") or ""])
                        human = server == "medrxiv"
                        c = candidate(
                            server, rid, title, f"https://doi.org/{rid}", text,
                            {"human": human, "preprint": True, "date": result.get("date"), "category": result.get("category")},
                            evidence="Human preprint" if human else "Preclinical/basic-science preprint",
                            source_quality="bioRxiv/medRxiv preprint server — not peer reviewed",
                        )
                        if c:
                            out.append(c)
                    fetched += len(collection)
                    if len(collection) < 30:
                        break
                    cursor += len(collection)
                except Exception as e:
                    warnings.append(f"{server} query failed for {category!r} ({type(e).__name__})")
                    break
    return out


def scan_reporter(warnings):
    out, seen = [], set()
    for query0 in CONFIG["nih_reporter_queries"]:
        try:
            payload = {
                "criteria": {
                    "advanced_text_search": {
                        "operator": "and",
                        "search_field": "projecttitle,abstracttext,terms",
                        "search_text": query0,
                    },
                    "include_active_projects": True,
                },
                "offset": 0,
                "limit": 100,
                "sort_field": "project_start_date",
                "sort_order": "desc",
            }
            data = post_json("https://api.reporter.nih.gov/v2/projects/search", payload)
            for result in data.get("results", []):
                rid = str(result.get("appl_id") or result.get("project_num") or result.get("core_project_num") or "")
                if not rid or rid in seen:
                    continue
                seen.add(rid)
                title = result.get("project_title") or rid
                text = " ".join([title, result.get("abstract_text") or "", " ".join(result.get("pref_terms") or [])])
                organization = result.get("organization") or {}
                c = candidate(
                    "NIH RePORTER", rid, title, "https://reporter.nih.gov/", text,
                    {
                        "grant": True,
                        "human": False,
                        "organization": organization.get("org_name") if isinstance(organization, dict) else None,
                        "start": result.get("project_start_date"),
                        "end": result.get("project_end_date"),
                        "fiscal_year": result.get("fiscal_year"),
                    },
                    evidence="Funded translational/basic research programme",
                    source_quality="US federal grant database",
                )
                if c:
                    out.append(c)
        except Exception as e:
            warnings.append(f"NIH RePORTER query failed: {query0!r} ({type(e).__name__})")
    return out


def scan_ctis(warnings):
    ids = set()
    for page in CONFIG.get("ctis_condition_pages", []):
        try:
            text, _ = html_text(req(page))
            ids.update(CTIS_RE.findall(text))
        except Exception as e:
            warnings.append(f"CTIS discovery page failed: {page} ({type(e).__name__})")
    out = []
    for tid in sorted(ids):
        if tid in KNOWN_IDS:
            continue
        mirror = f"https://ctis.eu/trial/{tid}"
        official = f"https://euclinicaltrials.eu/ctis-public/view/{tid}?lang=en"
        try:
            text, _ = html_text(req(mirror))
            title = text[:260] if text else tid
            c = candidate(
                "EU CTIS discovery", tid, title, official, text,
                {"human": True, "greece": "Greece" in text},
                evidence="EU human trial record",
                source_quality="Discovery via CTIS.eu; official EU CTIS record linked for verification",
            )
            if c:
                out.append(c)
        except Exception as e:
            warnings.append(f"CTIS trial fetch failed: {tid} ({type(e).__name__})")
    return out


def scan_anzctr(warnings):
    """Best-effort discovery using ANZCTR's public crawler pages."""
    out, ids = [], set()
    try:
        raw = req("https://www.anzctr.org.au/crawl.aspx")
        _, links = html_text(raw)
        crawl_pages = []
        for href, _anchor in links:
            url = urllib.parse.urljoin("https://www.anzctr.org.au/crawl.aspx", href)
            m = re.search(r"/crawl(\d+)\.aspx", url, re.I)
            if m:
                crawl_pages.append((int(m.group(1)), url))
        crawl_pages = [url for _, url in sorted(set(crawl_pages), reverse=True)[:4]]
        for page in crawl_pages:
            try:
                body, page_links = html_text(req(page))
                ids.update(ACTRN_RE.findall(body))
                for href, anchor in page_links:
                    ids.update(ACTRN_RE.findall(href + " " + anchor))
            except Exception as e:
                warnings.append(f"ANZCTR crawler bucket failed: {page} ({type(e).__name__})")
    except Exception as e:
        warnings.append(f"ANZCTR crawler index unavailable ({type(e).__name__})")
        return out

    for actrn in sorted(ids)[-350:]:
        if actrn.upper() in KNOWN_IDS:
            continue
        url = f"https://www.anzctr.org.au/Trial/Registration/TrialReview.aspx?ACTRN={urllib.parse.quote(actrn)}"
        try:
            record, _ = html_text(req(url))
            title_match = re.search(r"(?:Public title|Scientific title)\s+(.{10,240}?)(?:Trial acronym|Secondary ID|Health condition)", record, re.I)
            title = title_match.group(1).strip() if title_match else actrn
            c = candidate(
                "ANZCTR", actrn.upper(), title, url, record,
                {"human": True, "greece": "Greece" in record},
                evidence="Human trial registry record",
                source_quality="WHO primary registry (ANZCTR); crawler-based discovery, record verified on ANZCTR",
            )
            if c:
                out.append(c)
        except Exception as e:
            warnings.append(f"ANZCTR record fetch failed: {actrn} ({type(e).__name__})")
    return out


def scan_conferences(warnings):
    out, seen = [], set()
    for page in CONFIG.get("conference_pages", []):
        try:
            raw = req(page["url"])
            _, links = html_text(raw)
            selected = []
            for href, anchor in links:
                s = (href + " " + anchor).lower()
                if any(k in s for k in ("abstract", "poster", "program", "programme", "library", "scientific")):
                    selected.append((href, anchor))
            for href, anchor in selected[:20]:
                url = urllib.parse.urljoin(page["url"], href)
                if url in seen:
                    continue
                seen.add(url)
                try:
                    body, _ = html_text(req(url))
                except Exception:
                    continue
                title = anchor or body[:220] or url
                c = candidate(
                    page["name"], url, title, url, body,
                    {"human": any(x in body.lower() for x in ("patient", "participants", "phase 1", "phase i", "phase 2", "phase ii"))},
                    evidence="Conference/official programme discovery",
                    source_quality="Official conference source; abstract/full data require review",
                )
                if c:
                    out.append(c)
        except Exception as e:
            warnings.append(f"Conference source failed: {page['name']} ({type(e).__name__})")
    return out


def scan_news_rss(warnings):
    """Company/university discovery lead; primary-source verification is mandatory."""
    import xml.etree.ElementTree as ET
    out, seen = [], set()
    for query0 in CONFIG.get("news_queries", []):
        try:
            params = urllib.parse.urlencode({"q": query0, "hl": "en", "gl": "US", "ceid": "US:en"})
            raw = req("https://news.google.com/rss/search?" + params)
            root = ET.fromstring(raw)
            for item in root.findall(".//item")[:50]:
                title = item.findtext("title") or ""
                link = item.findtext("link") or ""
                desc = item.findtext("description") or ""
                stable = link or title
                if not stable or stable in seen:
                    continue
                seen.add(stable)
                text = " ".join([title, re.sub("<[^>]+>", " ", desc)])
                c = candidate(
                    "News discovery", stable, title, link, text,
                    {"human": any(x in text.lower() for x in ("clinical trial", "phase 1", "phase i", "phase 2", "phase ii", "patients"))},
                    evidence="Company/university/news lead",
                    source_quality="Secondary discovery only — primary source verification required",
                )
                if c:
                    out.append(c)
        except Exception as e:
            warnings.append(f"News RSS query failed: {query0!r} ({type(e).__name__})")
    return out


def key(c):
    return f"{c['source']}::{c['id']}"


def main():
    state = load_state()
    baseline = not STATE_PATH.exists() or not state.get("seen")
    previous = set()
    for values in state.get("seen", {}).values():
        previous.update(values)

    warnings = []
    sources = [
        ("clinicaltrials", scan_clinicaltrials),
        ("ctis", scan_ctis),
        ("europepmc", scan_europepmc),
        ("preprints", scan_preprints),
        ("nih_reporter", scan_reporter),
        ("anzctr", scan_anzctr),
        ("conferences", scan_conferences),
        ("news", scan_news_rss),
    ]

    all_candidates = []
    counts = {}
    current_seen = {k: list(v) for k, v in state.get("seen", {}).items()}
    for source_name, func in sources:
        try:
            candidates = func(warnings)
        except Exception as e:
            warnings.append(f"{source_name} scanner crashed ({type(e).__name__}: {e})")
            candidates = []
        dedup = {key(c): c for c in candidates}
        candidates = list(dedup.values())
        counts[source_name] = len(candidates)
        source_keys = sorted(key(c) for c in candidates)
        current_seen[source_name] = sorted(set(current_seen.get(source_name, [])) | set(source_keys))
        all_candidates.extend(candidates)

    new_candidates = [c for c in all_candidates if key(c) not in previous]
    report_candidates = [] if baseline else new_candidates
    report_candidates.sort(key=lambda x: (not x["greece_priority"], not x["human_data"], -x["score"], x["source"], x["title"]))

    save_state({
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "seen": current_seen,
    })

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline": baseline,
        "candidate_count": len(report_candidates),
        "source_candidate_counts": counts,
        "warnings": warnings,
        "candidates": report_candidates,
        "policy": {
            "auto_publish": False,
            "animal_cell_imaging_not_clinical_benefit": True,
            "primary_source_verification_required": True,
        },
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    core_fail = any("ClinicalTrials.gov" in w for w in warnings) and any("Europe PMC" in w for w in warnings)
    print(f"Baseline={baseline}; new candidates={len(report_candidates)}; warnings={len(warnings)}; source counts={counts}")
    return 2 if core_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
