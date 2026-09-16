#!/usr/bin/env python3
"""ANZCTR discovery fallback using a real headless browser.

ANZCTR can reject direct CI HTTP clients. Its search pages are browser-oriented,
so this scanner uses Chrome only as a last resort, then verifies candidate records
on ANZCTR itself. It merges results into the weekly discovery state/report.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
from pathlib import Path

import deep_discovery as dd

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "monitor" / "discovery_state.json"
REPORT_PATH = ROOT / "monitor" / "discovery_report.json"
ACTRN_RE = re.compile(r"\bACTRN\d{14}[A-Za-z]?\b", re.I)


def main() -> int:
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
    except Exception as e:
        print(f"ANZCTR browser fallback unavailable: selenium import failed ({type(e).__name__})")
        return 0

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1440,1200")
    options.add_argument("--lang=en-AU")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
    )

    ids: set[str] = set()
    browser_warnings: list[str] = []
    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(35)
        for query in dd.CONFIG.get("anzctr_queries", []):
            url = "https://www.anzctr.org.au/TrialSearch.aspx?" + urllib.parse.urlencode({
                "isBasic": "True",
                "searchTxt": query,
            })
            try:
                driver.get(url)
                # The site may populate results after initial page load.
                WebDriverWait(driver, 15).until(
                    lambda d: "ACTRN" in d.page_source or "No trial" in d.page_source or "No records" in d.page_source
                )
                time.sleep(1)
                ids.update(x.upper() for x in ACTRN_RE.findall(driver.page_source))
            except Exception as e:
                browser_warnings.append(f"ANZCTR browser query failed: {query!r} ({type(e).__name__})")

        candidates = []
        for actrn in sorted(ids):
            if actrn in dd.KNOWN_IDS:
                continue
            record_url = f"https://www.anzctr.org.au/{actrn}.aspx"
            try:
                driver.get(record_url)
                time.sleep(0.7)
                body = driver.find_element(By.TAG_NAME, "body").text
                title = actrn
                for label in ("Public title", "Scientific title"):
                    m = re.search(label + r"\s*[:\-]?\s*(.{12,300}?)(?:\n|Trial acronym|Secondary ID|Health condition)", body, re.I | re.S)
                    if m:
                        title = " ".join(m.group(1).split())
                        break
                c = dd.candidate(
                    "ANZCTR", actrn, title, record_url, body,
                    {"human": True, "greece": "Greece" in body},
                    evidence="Human trial registry record",
                    source_quality="WHO primary registry (ANZCTR); discovered and verified with browser access on ANZCTR",
                )
                if c:
                    candidates.append(c)
            except Exception as e:
                browser_warnings.append(f"ANZCTR browser record failed: {actrn} ({type(e).__name__})")
    except Exception as e:
        print(f"ANZCTR browser startup failed ({type(e).__name__}: {e})")
        return 0
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {"version": 1, "seen": {}}
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    previous = set()
    for source_keys in state.get("seen", {}).values():
        previous.update(source_keys)

    candidate_keys = {dd.key(c) for c in candidates}
    new_candidates = [c for c in candidates if dd.key(c) not in previous]
    state.setdefault("seen", {})["anzctr"] = sorted(set(state.get("seen", {}).get("anzctr", [])) | candidate_keys)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # If Chrome reached at least one query without query-level errors, treat ANZCTR
    # as available and replace direct-client warnings with any narrower browser warnings.
    if ids or not browser_warnings:
        report["warnings"] = [
            w for w in report.get("warnings", [])
            if not w.startswith("ANZCTR crawler index unavailable")
            and not w.startswith("ANZCTR crawler bucket failed")
        ]
        report.setdefault("source_candidate_counts", {})["anzctr"] = len(candidates)
    for warning in browser_warnings:
        if warning not in report.get("warnings", []):
            report.setdefault("warnings", []).append(warning)

    if not report.get("baseline"):
        existing = {dd.key(c) for c in report.get("candidates", [])}
        for c in new_candidates:
            if dd.key(c) not in existing:
                report.setdefault("candidates", []).append(c)
                existing.add(dd.key(c))

    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"ANZCTR browser IDs={len(ids)}; candidates={len(candidates)}; new={len(new_candidates)}; warnings={len(browser_warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
