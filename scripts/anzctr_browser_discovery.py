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
BLOCK_MARKERS = ("access denied", "forbidden", "captcha", "temporarily unavailable", "service unavailable")


def main() -> int:
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
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
    accessible_queries = 0
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
                # ANZCTR may return a legitimate empty result without a machine-readable
                # "no results" marker. Give client-side rendering a short fixed window,
                # then treat a normal registry page with zero ACTRN matches as zero results.
                time.sleep(3)
                source = driver.page_source
                low = source.lower()
                if any(marker in low for marker in BLOCK_MARKERS):
                    browser_warnings.append(f"ANZCTR browser access blocked for query: {query!r}")
                    continue
                if "australian new zealand clinical trials registry" in low or "trial search" in low or "anzctr" in low:
                    accessible_queries += 1
                ids.update(x.upper() for x in ACTRN_RE.findall(source))
            except Exception as e:
                browser_warnings.append(f"ANZCTR browser query failed: {query!r} ({type(e).__name__})")

        candidates = []
        for actrn in sorted(ids):
            if actrn in dd.KNOWN_IDS:
                continue
            record_url = f"https://www.anzctr.org.au/{actrn}.aspx"
            try:
                driver.get(record_url)
                time.sleep(0.8)
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

    from discovery_source_utils import merge_source
    if not accessible_queries and not browser_warnings:
        browser_warnings.append('ANZCTR browser returned no verifiable search page')
    print(json.dumps(merge_source('anzctr', candidates, browser_warnings)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
