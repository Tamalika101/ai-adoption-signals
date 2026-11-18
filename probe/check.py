"""Second feasibility probe (temporary branch, will be deleted)."""
import json, os, re, time, datetime as dt
import requests
S = requests.Session(); S.headers["User-Agent"] = "ai-adoption-signals probe"
GH = requests.Session(); GH.headers.update({"Authorization": f"Bearer {os.environ['GH_TOKEN']}", "Accept": "application/vnd.github+json"})
CHANGE = re.compile(r"\b(deploy\w*|roll(ed)?[ -]?back|revert\w*|recent change|config(uration)? change|release|rolled out|code change|migration)\b", re.I)

def safe(f):
    try: return f()
    except Exception as e: return {"error": repr(e)[:200]}

# 1. PostHog status page: what is it?
def posthog():
    out = {}
    for p in ["/", "/history", "/api/v2/incidents.json", "/history.rss", "/feed.rss", "/rss", "/proxy/status.posthog.com/incidents"]:
        r = S.get("https://status.posthog.com" + p, timeout=30)
        out[p] = [r.status_code, r.headers.get("content-type"), re.sub(r"\s+", " ", r.text[:300])]
    return out

# 2. GitLab public production incident tracker
def gitlab():
    base = "https://gitlab.com/api/v4/projects/gitlab-com%2Fgl-infra%2Fproduction/issues"
    first = S.get(base, params={"labels": "incident", "per_page": 3, "order_by": "created_at", "sort": "asc"}, timeout=60)
    last = S.get(base, params={"labels": "incident", "per_page": 20, "order_by": "created_at", "sort": "desc"}, timeout=60)
    out = {"status": [first.status_code, last.status_code], "total": last.headers.get("x-total")}
    if first.ok: out["oldest"] = [(i["created_at"][:10], i["title"][:80]) for i in first.json()]
    if last.ok:
        js = last.json()
        out["recent"] = [(i["created_at"][:10], i["title"][:80]) for i in js[:5]]
        labs = {}
        for i in js:
            for l in i["labels"]:
                if any(k in l for k in ("RootCause", "Severity", "Service")): labs[l] = labs.get(l, 0) + 1
        out["labels"] = labs
    # counts per year via x-total
    for y in (2023, 2024, 2025, 2026):
        r = S.get(base, params={"labels": "incident", "per_page": 1, "created_after": f"{y}-01-01", "created_before": f"{y}-12-31"}, timeout=60)
        out[f"n_{y}"] = r.headers.get("x-total")
        r = S.get(base, params={"labels": "incident,RootCause::Software-Change", "per_page": 1, "created_after": f"{y}-01-01", "created_before": f"{y}-12-31"}, timeout=60)
        out[f"n_{y}_rootcause_software_change"] = r.headers.get("x-total")
    return out

# 3. Change-caused share in status page incident texts (Atlassian history.json)
def change_share(url, pages=16):
    by_year = {}
    for p in range(1, pages + 1):
        j = S.get(f"{url}/history.json?page={p}", timeout=30).json()
        for m in j.get("months") or []:
            for inc in m.get("incidents") or []:
                y = m["year"]; d = by_year.setdefault(y, [0, 0])
                d[0] += 1
                d[1] += bool(CHANGE.search((inc.get("name") or "") + " " + (inc.get("message") or "")))
        time.sleep(0.5)
    return {y: {"incidents": a, "change_mentions": b} for y, (a, b) in sorted(by_year.items())}

def gh_count(q):
    for i in range(6):
        try:
            r = GH.get("https://api.github.com/search/commits", params={"q": q, "per_page": 1}, timeout=60)
            if r.status_code == 200:
                time.sleep(2.5); return r.json()["total_count"]
        except requests.RequestException:
            pass
        time.sleep(20 * (i + 1))
    return None

def repo(full):
    rows = []
    for a, b in [("2024-01-01", "2024-03-31"), ("2025-01-01", "2025-03-31"), ("2026-01-01", "2026-03-31"), ("2026-07-01", "2026-09-30")]:
        rng = f"committer-date:{a}..{b}"
        rows.append({"from": a, "commits": gh_count(f"repo:{full} {rng}"),
                     "ai_claude": gh_count(f'repo:{full} {rng} "co-authored-by: claude"'),
                     "revert_word": gh_count(f"repo:{full} {rng} revert")})
        print(full, rows[-1], flush=True)
    return rows

out = {}
out["posthog_status"] = safe(posthog); print("posthog", json.dumps(out["posthog_status"])[:1500], flush=True)
out["gitlab"] = safe(gitlab); print("gitlab", json.dumps(out["gitlab"])[:2500], flush=True)
for k, u in [("sentry", "https://status.sentry.io"), ("grafana", "https://status.grafana.com")]:
    out[f"change_{k}"] = safe(lambda: change_share(u)); print("change", k, out[f"change_{k}"], flush=True)
for r in ["grafana/mimir", "grafana/loki", "dagster-io/dagster", "PostHog/posthog", "getsentry/sentry"]:
    out[r] = safe(lambda: repo(r))
json.dump(out, open("probe_result.json", "w"), indent=1)
