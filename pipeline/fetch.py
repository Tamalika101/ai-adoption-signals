"""Download every source into data/raw/. Run: python -m pipeline.fetch [source ...]

Each source is independent: if one fails the others still run, and the build
step later reports which sections are missing rather than inventing data.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from io import StringIO

import pandas as pd
import requests

from . import config as C

S = requests.Session()
S.headers["User-Agent"] = C.USER_AGENT


def _get(url, *, params=None, headers=None, tries=4, timeout=60):
    for i in range(tries):
        try:
            r = S.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code in (403, 429, 503) and i < tries - 1:
                time.sleep(10 * (i + 1))
                continue
            r.raise_for_status()
            return r
        except requests.RequestException:
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def _save(name, obj):
    C.RAW.mkdir(parents=True, exist_ok=True)
    path = C.RAW / name
    if isinstance(obj, (bytes, bytearray)):
        path.write_bytes(obj)
    elif isinstance(obj, str):
        path.write_text(obj)
    else:
        path.write_text(json.dumps(obj))
    print(f"  saved {path.relative_to(C.ROOT)}")


# --- AI adoption -----------------------------------------------------------
def ramp():
    frames = []
    for sid in C.RAMP_SERIES:
        txt = _get(C.FRED_CSV.format(series=sid)).text
        df = pd.read_csv(StringIO(txt))
        df.columns = ["date", "value"]
        df["series"] = sid
        frames.append(df)
    out = pd.concat(frames)
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    _save("ramp.csv", out.dropna().to_csv(index=False))


def btos():
    _save("btos_national.xlsx", _get(C.BTOS_NATIONAL_XLSX).content)


# --- Cyber -----------------------------------------------------------------
def kev():
    _save("kev.json", _get(C.KEV_JSON).json())


def _nvd_headers():
    key = os.environ.get("NVD_API_KEY")
    return ({"apiKey": key} if key else {}), (C.NVD_DELAY_WITH_KEY if key else C.NVD_DELAY_NO_KEY)


def _nvd(params):
    headers, delay = _nvd_headers()
    time.sleep(delay)
    # Flags such as hasKev must be sent without "=": build that part by hand.
    flags = "&".join(k for k, v in params.items() if v == "")
    rest = {k: v for k, v in params.items() if v != ""}
    url = C.NVD_API + ("?" + flags if flags else "")
    return _get(url, params=rest, headers=headers, timeout=120).json()


def _nvd_all(params):
    """Page through an NVD query, returning the list of 'cve' objects."""
    out, start = [], 0
    while True:
        j = _nvd({**params, "resultsPerPage": 2000, "startIndex": start})
        out += [v["cve"] for v in j.get("vulnerabilities", [])]
        start += j.get("resultsPerPage", 0)
        if start >= j.get("totalResults", 0) or not j.get("resultsPerPage"):
            return out


def _slim(cve):
    desc = next((d["value"] for d in cve.get("descriptions", []) if d["lang"] == "en"), "")
    score = None
    for key in ("cvssMetricV31", "cvssMetricV40", "cvssMetricV30"):
        m = cve.get("metrics", {}).get(key)
        if m:
            score = m[0]["cvssData"].get("baseScore")
            break
    return {"id": cve["id"], "published": cve["published"][:10], "score": score,
            "status": cve.get("vulnStatus"), "description": desc[:400]}


def _quarters(start: str):
    d = date.fromisoformat(start + "-01")
    today = date.today()
    while d <= today:
        nxt = date(d.year + (d.month + 2) // 12, (d.month + 2) % 12 + 1, 1)
        yield d, min(nxt - timedelta(days=1), today)
        d = nxt


def nvd_kev():
    """Publication date of every CVE in the KEV catalogue (NVD hasKev filter)."""
    _save("nvd_kev.json", [_slim(c) for c in _nvd_all({"hasKev": ""})])


def nvd_ai():
    """AI-software CVEs per keyword, plus total CVEs published each month.

    Results for periods that ended more than 90 days ago are cached in
    data/archive/nvd_cache.json (committed), so weekly runs only re-query
    recent months instead of ~400 slow API calls.
    """
    cache_path = C.ARCHIVE / "nvd_cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    settled = date.today() - timedelta(days=90)
    found = {}
    for kw in C.AI_KEYWORDS:
        for a, b in _quarters(C.START_MONTH):
            key = f"kw|{kw}|{a}"
            if key in cache:
                cves = cache[key]
            else:
                params = {"keywordSearch": kw,
                          "pubStartDate": f"{a}T00:00:00.000", "pubEndDate": f"{b}T23:59:59.999"}
                cves = [_slim(c) for c in _nvd_all(params)]
                if b < settled:
                    cache[key] = cves
            for rec in cves:
                found.setdefault(rec["id"], {**rec, "keywords": []})["keywords"].append(kw)
        print(f"  {kw}: {sum(kw in r['keywords'] for r in found.values())} CVEs")
    totals = []
    for a, b in _months(C.START_MONTH):
        key = f"total|{a}"
        if key in cache:
            n = cache[key]
        else:
            j = _nvd({"pubStartDate": f"{a}T00:00:00.000", "pubEndDate": f"{b}T23:59:59.999",
                      "resultsPerPage": 1})
            n = j.get("totalResults", 0)
            if b < settled:
                cache[key] = n
        totals.append({"month": a.strftime("%Y-%m"), "total": n})
    C.ARCHIVE.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, sort_keys=True))
    _save("nvd_ai.json", {"cves": list(found.values()), "monthly_totals": totals})


def _months(start: str):
    d = date.fromisoformat(start + "-01")
    today = date.today()
    while d <= today:
        nxt = date(d.year + d.month // 12, d.month % 12 + 1, 1)
        yield d, min(nxt - timedelta(days=1), today)
        d = nxt


# --- Service reliability ---------------------------------------------------
_TAG = re.compile(r"<[^>]+>")


def statuspages():
    stop = int(C.START_MONTH[:4])
    for key, cfg in C.STATUSPAGES.items():
        rows, page = [], 1
        while True:
            j = _get(f"{cfg['url']}/history.json", params={"page": page}).json()
            months = j.get("months") or []
            if not months:
                break
            for m in months:
                for inc in m.get("incidents") or []:
                    rows.append({"year": m["year"], "month": m["name"], "code": inc.get("code"),
                                 "name": inc.get("name"), "impact": inc.get("impact"),
                                 "when": _TAG.sub("", inc.get("timestamp") or "")})
            if min(m["year"] for m in months) < stop or page > 60:
                break
            page += 1
            time.sleep(1)
        _save(f"status_{key}.json", rows)


def openai_status():
    """Merge the current RSS feed into our own committed archive."""
    xml = _get(C.OPENAI_RSS).text
    items = re.findall(r"<item>(.*?)</item>", xml, flags=re.S)
    path = C.ARCHIVE / "openai_incidents.json"
    archive = json.loads(path.read_text()) if path.exists() else {}
    for it in items:
        guid = re.search(r"<guid[^>]*>(.*?)</guid>", it, re.S)
        title = re.search(r"<title>(.*?)</title>", it, re.S)
        pub = re.search(r"<pubDate>(.*?)</pubDate>", it, re.S)
        link = re.search(r"<link>(.*?)</link>", it, re.S)
        ident = (guid or link).group(1).strip()
        when = parsedate_to_datetime(pub.group(1)).astimezone(timezone.utc).isoformat()
        rec = archive.setdefault(ident, {"title": _unescape(title.group(1)), "first_seen": when})
        rec["first_seen"] = min(rec["first_seen"], when)
    C.ARCHIVE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(archive, indent=1, sort_keys=True))
    print(f"  openai archive: {len(archive)} incidents")


def _unescape(s):
    s = re.sub(r"^<!\[CDATA\[(.*)\]\]>$", r"\1", s.strip(), flags=re.S)
    return s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'").replace("&quot;", '"')


# --- Internet outages ------------------------------------------------------
def cloudflare():
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        print("  CLOUDFLARE_API_TOKEN not set; skipping internet outages")
        return
    rows, offset = [], 0
    params = {"dateStart": f"{C.START_MONTH}-01T00:00:00Z",
              "dateEnd": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "limit": 500, "format": "json"}
    while True:
        j = _get(C.CF_OUTAGES, params={**params, "offset": offset},
                 headers={"Authorization": f"Bearer {token}"}).json()
        batch = j.get("result", {}).get("annotations", [])
        for a in batch:
            o = a.get("outage") or {}
            rows.append({"id": a.get("id"), "start": a.get("startDate"), "end": a.get("endDate"),
                         "cause": o.get("outageCause"), "type": o.get("outageType"),
                         "locations": a.get("locations"), "description": a.get("description")})
        if len(batch) < params["limit"]:
            break
        offset += params["limit"]
    _save("cloudflare_outages.json", rows)


SOURCES = {"ramp": ramp, "btos": btos, "kev": kev, "nvd_kev": nvd_kev, "nvd_ai": nvd_ai,
           "statuspages": statuspages, "openai_status": openai_status, "cloudflare": cloudflare}


def main(names):
    failed = []
    for name in names or SOURCES:
        print(f"[{name}]")
        try:
            SOURCES[name]()
        except Exception as e:  # keep going; the build step reports gaps
            print(f"  FAILED: {e!r}")
            failed.append(name)
    if failed:
        print("Failed sources:", ", ".join(failed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
