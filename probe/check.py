"""One-off feasibility probe (temporary branch, will be deleted)."""
import json, os, re, time, datetime as dt
import requests
S = requests.Session(); S.headers["User-Agent"] = "ai-adoption-signals probe"
GH = requests.Session(); GH.headers.update({"Authorization": f"Bearer {os.environ['GH_TOKEN']}", "Accept": "application/vnd.github+json"})

STATUS = {
  "sentry": ["https://status.sentry.io"], "supabase": ["https://status.supabase.com"],
  "posthog": ["https://status.posthog.com"], "grafana": ["https://status.grafana.com"],
  "mattermost": ["https://status.mattermost.com", "https://status.mattermost.cloud"],
  "calcom": ["https://status.cal.com", "https://cal.openstatus.dev"], "n8n": ["https://status.n8n.cloud", "https://status.n8n.io"],
  "gitlab": ["https://status.gitlab.com"], "vercel": ["https://www.vercel-status.com"],
  "netlify": ["https://www.netlifystatus.com"], "cloudflare": ["https://www.cloudflarestatus.com"],
  "airbyte": ["https://status.airbyte.com"], "appsmith": ["https://status.appsmith.com"],
  "hasura": ["https://status.hasura.io"], "infisical": ["https://status.infisical.com"],
  "langfuse": ["https://status.langfuse.com"], "dagster": ["https://dagstercloud.statuspage.io", "https://status.dagster.io"],
  "metabase": ["https://status.metabase.com"], "zulip": ["https://status.zulip.com"], "discourse": ["https://status.discourse.org"],
}
REPOS = {"sentry": "getsentry/sentry", "supabase": "supabase/supabase", "posthog": "PostHog/posthog",
  "grafana": "grafana/grafana", "mattermost": "mattermost/mattermost", "calcom": "calcom/cal.com",
  "n8n": "n8n-io/n8n", "airbyte": "airbytehq/airbyte", "appsmith": "appsmithorg/appsmith",
  "hasura": "hasura/graphql-engine", "infisical": "Infisical/infisical", "langfuse": "langfuse/langfuse",
  "dagster": "dagster-io/dagster", "metabase": "metabase/metabase", "zulip": "zulip/zulip", "discourse": "discourse/discourse"}

def status(url):
    out = {"url": url}
    try:
        r = S.get(url + "/history.json?page=1", timeout=30)
        if r.ok and "months" in r.text:
            pages, earliest, n = 1, None, 0
            while pages <= 40:
                j = S.get(url + f"/history.json?page={pages}", timeout=30).json()
                ms = j.get("months") or []
                if not ms: break
                for m in ms:
                    n += len(m.get("incidents") or [])
                    earliest = f"{m['year']}-{m['name'][:3]}"
                if all(not m.get("incidents") for m in ms) and pages > 3: break
                pages += 1; time.sleep(0.5)
            j1 = S.get(url + "/api/v2/incidents.json", timeout=30).json()
            sample = [i["name"] for i in j1.get("incidents", [])[:40]]
            out.update(kind="atlassian", earliest=earliest, incidents=n, pages=pages - 1,
                       change_words=sum(bool(re.search(r"deploy|rollback|roll back|revert|release|change|config", s, re.I)) for s in sample),
                       sample=sample[:6])
            return out
        r = S.get(url + "/api/v2/incidents.json", timeout=30)
        if r.ok and "incidents" in r.text:
            inc = r.json()["incidents"]
            out.update(kind="statuspage-api-only", n=len(inc), oldest=inc[-1]["created_at"] if inc else None)
        for feed in ("/history.rss", "/feed.rss", "/rss", "/feed"):
            f = S.get(url + feed, timeout=30)
            if f.ok and "<item" in f.text:
                d = re.findall(r"<pubDate>([^<]+)</pubDate>", f.text)
                out.update(feed=feed, feed_items=len(d), feed_oldest=d[-1] if d else None); break
        if "kind" not in out:
            out.update(kind="unknown", http=r.status_code, server=r.headers.get("server"))
    except Exception as e:
        out.update(kind="error", error=repr(e)[:200])
    return out

def gh_count(q):
    for i in range(5):
        r = GH.get("https://api.github.com/search/commits", params={"q": q, "per_page": 1}, timeout=60)
        if r.status_code == 200:
            time.sleep(2.2); return r.json()["total_count"]
        time.sleep(30 * (i + 1))
    return None

def repo(full):
    meta = GH.get(f"https://api.github.com/repos/{full}").json()
    res = {"repo": full, "pushed": meta.get("pushed_at"), "archived": meta.get("archived"), "rows": []}
    for y, q1 in [(2023, "01"), (2024, "01"), (2025, "01"), (2025, "07"), (2026, "01"), (2026, "07")]:
        a = f"{y}-{q1}-01"; b = (dt.date(y, int(q1), 1) + dt.timedelta(days=89)).isoformat()
        rng = f"committer-date:{a}..{b}"
        row = {"from": a,
               "commits": gh_count(f"repo:{full} {rng}"),
               "ai_claude": gh_count(f'repo:{full} {rng} "co-authored-by: claude"'),
               "ai_copilot": gh_count(f'repo:{full} {rng} "co-authored-by: copilot"'),
               "ai_cursor": gh_count(f'repo:{full} {rng} "cursor agent"'),
               "reverts": gh_count(f'repo:{full} {rng} "this reverts commit"')}
        res["rows"].append(row)
        print(full, row, flush=True)
    return res

out = {"status": {}, "repos": {}}
for k, urls in STATUS.items():
    for u in urls:
        s = status(u); print(k, json.dumps(s)[:400], flush=True)
        out["status"][k] = s
        if s["kind"] not in ("unknown", "error"): break
for k, r in REPOS.items():
    out["repos"][k] = repo(r)
json.dump(out, open("probe_result.json", "w"), indent=1)
