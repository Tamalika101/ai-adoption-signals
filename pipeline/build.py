"""Turn data/raw/ into the JSON the website reads. Run: python -m pipeline.build"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from . import config as C

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], start=1)}


def _raw(name):
    path = C.RAW / name
    return path if path.exists() else None


def _load_json(name):
    p = _raw(name)
    return json.loads(p.read_text()) if p else None


def complete_months(today: date | None = None) -> str:
    """Last fully finished month, e.g. '2026-10' when run in November."""
    today = today or date.today()
    first = today.replace(day=1)
    return (first - timedelta(days=1)).strftime("%Y-%m")


def series_to_records(s: pd.Series):
    return [{"month": k, "value": (None if pd.isna(v) else round(float(v), 4))} for k, v in s.items()]


# --- Adoption ------------------------------------------------------------------
def ramp_monthly():
    p = _raw("ramp.csv")
    if not p:
        return None
    df = pd.read_csv(p)
    df["month"] = df["date"].str[:7]
    wide = df.pivot_table(index="month", columns="series", values="value")
    return wide[wide.index >= C.START_MONTH]


AI_Q = re.compile(r"(artificial intelligence|super intelligence|\bAI\b|\bSI\b)", re.I)


def btos_biweekly():
    """National share of businesses using AI, one row per two-week survey."""
    p = _raw("btos_national.xlsx")
    if not p:
        return None
    from openpyxl import load_workbook
    wb = load_workbook(p, read_only=True, data_only=True)
    est = [r for r in wb["Response Estimates"].iter_rows(values_only=True)]
    header = [str(h) if h is not None else "" for h in est[0]]
    rows = []
    for r in est[1:]:
        q, ans = str(r[1] or ""), str(r[3] or "")
        if ans != "Yes" or not AI_Q.search(q) or not q.lower().startswith("in the last two weeks"):
            continue
        if "business functions" in q:
            kind = "Any business function"
        elif "producing goods or services" in q:
            kind = "Producing goods or services"
        else:
            continue
        for col, val in zip(header[4:], r[4:]):
            if isinstance(val, str) and val.endswith("%"):
                rows.append({"period": col, "kind": kind, "value": float(val[:-1])})
            elif isinstance(val, (int, float)):
                rows.append({"period": col, "kind": kind, "value": float(val) * (100 if val <= 1 else 1)})
    dates = {}
    cal = list(wb["Collection and Reference Dates"].iter_rows(values_only=True))
    head = [str(h or "") for h in cal[0]]
    i_p, i_s, i_e = head.index("Smpdt"), head.index("Collection Start"), head.index("Col End")
    for r in cal[1:]:
        if r[i_p] is None:
            continue
        dates[str(r[i_p])] = (_xl_date(r[i_s]), _xl_date(r[i_e]))
    df = pd.DataFrame(rows)
    if df.empty:
        return None
    df["start"] = df["period"].map(lambda k: dates.get(k, (None, None))[0])
    df["end"] = df["period"].map(lambda k: dates.get(k, (None, None))[1])
    return df.dropna(subset=["end"]).sort_values("end")


def _xl_date(v):
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, (int, float)):
        return (date(1899, 12, 30) + timedelta(days=int(v))).isoformat()
    return None


def btos_monthly(bi):
    if bi is None:
        return None
    cur = bi[bi["kind"] == "Any business function"].copy()
    cur["month"] = cur["end"].str[:7]
    return cur.groupby("month")["value"].mean()


# --- Cyber ---------------------------------------------------------------------
def kev_frame():
    kev = _load_json("kev.json")
    if not kev:
        return None
    df = pd.DataFrame(kev["vulnerabilities"])
    df["added"] = pd.to_datetime(df["dateAdded"])
    nvd = _load_json("nvd_kev.json")
    if nvd:
        pub = {r["id"]: r["published"] for r in nvd}
        score = {r["id"]: r["score"] for r in nvd}
        df["published"] = pd.to_datetime(df["cveID"].map(pub))
        df["score"] = df["cveID"].map(score)
        df["lag_days"] = (df["added"] - df["published"]).dt.days
    df["ai"] = (df["vendorProject"] + " " + df["product"] + " " + df["vulnerabilityName"]).str.contains(
        C.AI_KEV_PATTERN, case=False, regex=True)
    df["month"] = df["added"].dt.strftime("%Y-%m")
    return df


def kev_monthly(df, last_month):
    if df is None:
        return {}
    d = df[(df["month"] >= C.START_MONTH) & (df["month"] <= last_month)]
    g = d.groupby("month")
    out = {"kev_added": g.size(),
           "kev_ransomware_share": g["knownRansomwareCampaignUse"].apply(lambda s: 100 * (s == "Known").mean())}
    if "lag_days" in d:
        recent = d[d["published"] >= "2022-01-01"]
        gr = recent.groupby("month")["lag_days"]
        out["kev_median_lag"] = gr.median()
        out["kev_fast_share"] = d.groupby("month")["lag_days"].apply(lambda s: 100 * (s.dropna() <= 7).mean())
    idx = pd.Index(_month_range(C.START_MONTH, last_month))
    return {k: v.reindex(idx).fillna(0 if k == "kev_added" else np.nan) for k, v in out.items()}


def kev_quarterly(df, last_month):
    if df is None or "lag_days" not in df:
        return []
    d = df[(df["month"] >= C.START_MONTH) & (df["month"] <= last_month)].copy()
    d["q"] = d["added"].dt.to_period("Q").astype(str)
    rows = []
    for q, s in d.groupby("q"):
        lag = s["lag_days"].dropna()
        rows.append({"quarter": q, "added": int(len(s)),
                     "within_7d": round(100 * (lag <= 7).mean(), 1) if len(lag) else None,
                     "within_30d": round(100 * (lag <= 30).mean(), 1) if len(lag) else None,
                     "median_lag_recent": (float(s.loc[s["published"] >= "2022-01-01", "lag_days"].median())
                                           if (s["published"] >= "2022-01-01").any() else None),
                     "ai_entries": int(s["ai"].sum())})
    return rows


def nvd_ai_monthly(last_month):
    j = _load_json("nvd_ai.json")
    if not j:
        return {}, []
    cves = pd.DataFrame(j["cves"])
    tot = pd.DataFrame(j["monthly_totals"]).set_index("month")["total"]
    idx = pd.Index(_month_range(C.START_MONTH, last_month))
    if cves.empty:
        return {}, []
    cves["month"] = cves["published"].str[:7]
    cves = cves[cves["status"] != "Rejected"]
    count = cves.groupby("month").size().reindex(idx).fillna(0)
    share = (1000 * count / tot.reindex(idx)).replace([np.inf], np.nan)
    by_kw = {kw: int(sum(kw in k for k in cves["keywords"])) for kw in C.AI_KEYWORDS}
    top = cves.sort_values(["score", "published"], ascending=False).head(25)
    return ({"ai_cves": count, "ai_cves_per_1000": share, "all_cves": tot.reindex(idx)},
            {"by_keyword": by_kw, "top": top[["id", "published", "score", "description", "keywords"]].to_dict("records"),
             "total": int(len(cves))})


# --- Reliability -----------------------------------------------------------------
def status_monthly(key, last_month, focus=None):
    rows = _load_json(f"status_{key}.json")
    if rows is None:
        return None
    idx = pd.Index(_month_range(C.START_MONTH, last_month))
    df = pd.DataFrame(rows)
    if df.empty:
        return {"all": pd.Series(0, index=idx)}
    df["mon"] = df.apply(lambda r: f"{int(r['year'])}-{MONTHS[r['month']]:02d}", axis=1)
    out = {"all": df.groupby("mon").size().reindex(idx).fillna(0),
           "major": df[df["impact"].isin(["major", "critical"])].groupby("mon").size().reindex(idx).fillna(0)}
    if focus:
        f = df[df["name"].str.contains(focus, case=False, na=False)]
        out["focus"] = f.groupby("mon").size().reindex(idx).fillna(0)
    return out


def openai_monthly(last_month):
    path = C.ARCHIVE / "openai_incidents.json"
    if not path.exists():
        return None
    arc = json.loads(path.read_text())
    if not arc:
        return None
    s = pd.Series([v["first_seen"][:7] for v in arc.values()]).value_counts().sort_index()
    first = min(v["first_seen"] for v in arc.values())[:7]
    # The first month in the archive is only partly covered, so it is dropped.
    months = _month_range(first, last_month)[1:]
    return s.reindex(months).fillna(0) if months else None


def cloudflare_monthly(last_month):
    rows = _load_json("cloudflare_outages.json")
    if rows is None:
        return None
    idx = pd.Index(_month_range(C.START_MONTH, last_month))
    df = pd.DataFrame(rows)
    if df.empty:
        return {"all": pd.Series(0, index=idx)}, {}
    df["mon"] = df["start"].str[:7]
    causes = df["cause"].fillna("UNKNOWN").value_counts().to_dict()
    out = {"all": df.groupby("mon").size().reindex(idx).fillna(0),
           "cyber": df[df["cause"].fillna("").str.contains("CYBER|ATTACK", case=False)]
           .groupby("mon").size().reindex(idx).fillna(0)}
    return out, causes


# --- Statistics ----------------------------------------------------------------------
def spearman(a: pd.Series, b: pd.Series):
    return float(a.rank().corr(b.rank()))


def correlate(x: pd.Series, y: pd.Series, seed=7):
    """Spearman correlation on levels and on month-to-month changes.

    The change version is the honest one: two series that both trend upward
    always look correlated in levels. The p-value is a permutation test on
    the changes (share of shuffles with |rho| at least as large).
    """
    df = pd.concat([x.rename("x"), y.rename("y")], axis=1).dropna()
    res = {"n_months": int(len(df)), "from": df.index.min() if len(df) else None,
           "to": df.index.max() if len(df) else None}
    if len(df) < 8:
        return {**res, "level_rho": None, "change_rho": None, "p_value": None, "reading": "too little data"}
    res["level_rho"] = round(spearman(df["x"], df["y"]), 3)
    d = df.diff().dropna()
    if d["x"].nunique() < 3 or d["y"].nunique() < 3:
        return {**res, "change_rho": None, "p_value": None, "reading": "too little variation"}
    rho = spearman(d["x"], d["y"])
    rng = np.random.default_rng(seed)
    xr, yr = d["x"].rank().to_numpy(), d["y"].rank().to_numpy()
    hits = sum(abs(np.corrcoef(xr, rng.permutation(yr))[0, 1]) >= abs(rho) - 1e-12
               for _ in range(C.PERMUTATIONS))
    p = (hits + 1) / (C.PERMUTATIONS + 1)
    res.update(change_rho=round(rho, 3), p_value=round(p, 4), reading=_reading(rho, p))
    return res


def _reading(rho, p):
    band = next(label for cut, label in C.RHO_BANDS if abs(rho) < cut)
    if band == "none" or p >= 0.05:
        return "no reliable link"
    return f"{band} {'positive' if rho > 0 else 'negative'} link"


def _month_range(a: str, b: str):
    out, y, m = [], int(a[:4]), int(a[5:7])
    while f"{y}-{m:02d}" <= b:
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


# --- Main ------------------------------------------------------------------------
def build(today: date | None = None):
    last = complete_months(today)
    C.OUT.mkdir(parents=True, exist_ok=True)
    status = {}

    ramp = ramp_monthly()
    bi = btos_biweekly()
    bm = btos_monthly(bi)
    adoption = {
        "ramp": {sid: series_to_records(ramp[sid].dropna()) for sid in C.RAMP_SERIES if ramp is not None and sid in ramp},
        "ramp_labels": C.RAMP_SERIES,
        "btos": [] if bi is None else bi[["period", "kind", "start", "end", "value"]].to_dict("records"),
    }
    status["Ramp AI Index (FRED)"] = ramp is not None
    status["Census BTOS"] = bi is not None

    kev = kev_frame()
    metrics = {}
    labels = {}
    for k, v in kev_monthly(kev, last).items():
        metrics[k] = v
    labels.update(kev_added="Vulnerabilities newly confirmed as exploited (CISA KEV)",
                  kev_ransomware_share="% of those used in ransomware",
                  kev_median_lag="Median days from public disclosure to confirmed exploitation",
                  kev_fast_share="% confirmed exploited within 7 days of disclosure")
    status["CISA KEV"] = kev is not None
    status["NVD (KEV dates)"] = kev is not None and "lag_days" in kev

    ai_m, ai_detail = nvd_ai_monthly(last)
    metrics.update(ai_m)
    labels.update(ai_cves="New vulnerabilities in AI software (NVD)",
                  ai_cves_per_1000="AI-software vulnerabilities per 1,000 new CVEs",
                  all_cves="All new vulnerabilities published (NVD)")
    status["NVD (AI software)"] = bool(ai_m)

    for key, cfg in C.STATUSPAGES.items():
        sm = status_monthly(key, last, cfg.get("focus"))
        status[f"{cfg['label']} status page"] = sm is not None
        if sm:
            metrics[f"{key}_incidents"] = sm["all"]
            metrics[f"{key}_major"] = sm["major"]
            labels[f"{key}_incidents"] = f"{cfg['label']} incidents per month"
            labels[f"{key}_major"] = f"{cfg['label']} major/critical incidents per month"
            if "focus" in sm:
                metrics[f"{key}_focus"] = sm["focus"]
                labels[f"{key}_focus"] = f"{cfg['label']} incidents naming {cfg['focus']}"
    oa = openai_monthly(last)
    if oa is not None:
        metrics["openai_incidents"] = oa
        labels["openai_incidents"] = "OpenAI incidents per month (our archive)"
    status["OpenAI status (archive)"] = oa is not None

    cf = cloudflare_monthly(last)
    causes = {}
    if cf:
        cfm, causes = cf
        metrics["internet_outages"] = cfm["all"]
        metrics["internet_outages_cyber"] = cfm["cyber"]
        labels.update(internet_outages="Internet outages worldwide (Cloudflare Radar)",
                      internet_outages_cyber="…of which caused by cyberattacks")
    status["Cloudflare Radar"] = cf is not None

    # Correlations against each adoption measure.
    drivers = {}
    if ramp is not None and "RAMPAIALL" in ramp:
        drivers["ramp"] = ("Ramp AI Index (all businesses)", ramp["RAMPAIALL"][ramp.index <= last])
    if bm is not None:
        drivers["btos"] = ("Census BTOS (share using AI)", bm[bm.index <= last])
    corr = []
    for mk, ms in metrics.items():
        if mk == "all_cves":
            continue
        for dk, (dl, ds) in drivers.items():
            corr.append({"metric": mk, "metric_label": labels[mk], "driver": dk, "driver_label": dl,
                         **correlate(ds, ms)})

    out = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "through": last,
        "sources_ok": status,
        "adoption": adoption,
        "metrics": {k: series_to_records(v) for k, v in metrics.items()},
        "labels": labels,
        "correlations": corr,
        "kev_quarterly": kev_quarterly(kev, last),
        "kev_ai": ([] if kev is None else kev[kev["ai"]].sort_values("added", ascending=False)
                   [["cveID", "vendorProject", "product", "vulnerabilityName", "dateAdded",
                     "knownRansomwareCampaignUse"]].to_dict("records")),
        "kev_total": None if kev is None else int(len(kev)),
        "ai_cves": ai_detail,
        "outage_causes": causes,
    }
    (C.OUT / "site.json").write_text(json.dumps(_clean(out), default=_default, allow_nan=False))
    return out


def _clean(o):
    """Replace NaN with null so the file is valid JSON."""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, float) and np.isnan(o):
        return None
    if isinstance(o, np.floating):
        return None if np.isnan(o) else float(o)
    return o


def _default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (pd.Timestamp, date)):
        return o.isoformat()[:10]
    raise TypeError(type(o))


if __name__ == "__main__":
    o = build()
    print("through", o["through"])
    for k, v in o["sources_ok"].items():
        print(f"  {'ok ' if v else 'MISSING'} {k}")
    for c in o["correlations"]:
        print(f"  {c['driver']:4} vs {c['metric']:24} n={c['n_months']:3} level={c['level_rho']} "
              f"change={c['change_rho']} p={c['p_value']} -> {c['reading']}")
