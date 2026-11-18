import json
from datetime import date

import numpy as np
import pandas as pd

from pipeline import build as B
from pipeline import config as C


def test_trend_alone_is_not_a_link():
    # Two unrelated series that both rise: strong in levels, nothing in changes.
    rng = np.random.default_rng(1)
    idx = B._month_range("2023-01", "2026-06")
    x = pd.Series(np.arange(len(idx)) + rng.normal(0, 1, len(idx)), index=idx)
    y = pd.Series(2 * np.arange(len(idx)) + rng.normal(0, 3, len(idx)), index=idx)
    r = B.correlate(x, y)
    assert r["level_rho"] > 0.9
    assert r["reading"] == "no reliable link"


def test_shared_shocks_are_detected():
    rng = np.random.default_rng(2)
    idx = B._month_range("2023-01", "2026-06")
    shocks = rng.normal(0, 1, len(idx))
    x = pd.Series(np.cumsum(shocks), index=idx)
    y = pd.Series(np.cumsum(shocks + rng.normal(0, 0.3, len(idx))), index=idx)
    r = B.correlate(x, y)
    assert r["change_rho"] > 0.7 and r["p_value"] < 0.01
    assert r["reading"].startswith("strong positive")


def test_short_series_is_flagged():
    idx = B._month_range("2026-01", "2026-05")
    s = pd.Series(range(5), index=idx, dtype=float)
    assert B.correlate(s, s)["reading"] == "too little data"


def test_complete_months():
    assert B.complete_months(date(2026, 11, 17)) == "2026-10"
    assert B.complete_months(date(2027, 1, 3)) == "2026-12"


def test_status_months(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "RAW", tmp_path)
    rows = [{"year": 2026, "month": "March", "name": "Copilot slow", "impact": "major"},
            {"year": 2026, "month": "March", "name": "API errors", "impact": "minor"},
            {"year": 2026, "month": "May", "name": "Login", "impact": "none"}]
    (tmp_path / "status_x.json").write_text(json.dumps(rows))
    monkeypatch.setattr(C, "START_MONTH", "2026-02")
    out = B.status_monthly("x", "2026-05", focus="Copilot")
    assert out["all"].tolist() == [0, 2, 0, 1]
    assert out["major"].tolist() == [0, 1, 0, 0]
    assert out["focus"].tolist() == [0, 1, 0, 0]


def test_btos_parsing(tmp_path, monkeypatch):
    from openpyxl import Workbook
    monkeypatch.setattr(C, "RAW", tmp_path)
    wb = Workbook()
    ws = wb.active
    ws.title = "Response Estimates"
    q = ("In the last two weeks, did this business use Artificial Intelligence (AI) "
         "in any of its business functions?")
    ws.append(["Question ID", "Question", "Answer ID", "Answer", "202602", "202601"])
    ws.append([7, q, 1, "Yes", "18.2%", "17.7%"])
    ws.append([7, q, 2, "No", "70.0%", "71.0%"])
    cal = wb.create_sheet("Collection and Reference Dates")
    cal.append(["Sample Year", "Cycle", "Panel", "Smpdt", "Collection Start", "Col End"])
    cal.append([3, 1, 1, 202601, 46006, 46019])
    cal.append([None, 1, 2, 202602, 46020, 46033])
    wb.save(tmp_path / "btos_national.xlsx")
    bi = B.btos_biweekly()
    assert bi["value"].tolist() == [17.7, 18.2]
    assert bi["end"].tolist() == ["2025-12-28", "2026-01-11"]
