# AI Adoption Signals

**Does business AI adoption move together with cyber attacks and service outages?**

A static website, rebuilt every Monday by GitHub Actions from official and public data. It compares two measures
of US business AI adoption with measures of digital risk:

| Theme | Measure | Source |
|---|---|---|
| AI adoption | Share of businesses paying for AI tools (monthly) | Ramp AI Index via FRED |
| AI adoption | Share of employers using AI in the last two weeks (biweekly) | Census Bureau BTOS |
| Cyber attacks | Vulnerabilities newly confirmed as exploited, ransomware share, time from disclosure to exploitation | CISA KEV + NIST NVD |
| New attack surface | New CVEs in AI/ML software, raw and per 1,000 CVEs | NIST NVD |
| Service disruptions | Monthly incidents on the Claude, GitHub (Copilot) and OpenAI status pages | Official status pages |
| Internet outages | Outages worldwide by cause, including cyberattacks | Cloudflare Radar |

## Method in one paragraph

Two series that both rise over time always correlate. So for every measure the site reports Spearman's ρ on the
raw monthly **levels** and on the month-to-month **changes**, with a 5,000-shuffle permutation p-value for the changes.
Only same-month changes are compared (no lag hunting). A measure counts as linked only if |ρ| ≥ 0.1 on changes and
p < 0.05. Correlation is not causation.

## Run it locally

```bash
pip install -r requirements.txt
python -m pipeline.fetch        # downloads to data/raw/ (NVD part is slow without a key)
python -m pipeline.build        # writes site/data/site.json and prints the scorecard
python -m http.server -d site   # open http://localhost:8000
python -m pytest -q
```

Optional repository secrets:

- `CLOUDFLARE_API_TOKEN`: a free Cloudflare token with *Account → Radar → Read*, enables the internet-outages section.
- `NVD_API_KEY`: a free NVD key, makes the vulnerability download about 10× faster.

## Files

- `pipeline/config.py`: every source URL, keyword list and setting
- `pipeline/fetch.py`: downloads each source independently (a failing source never blocks the others)
- `pipeline/build.py`: monthly series, correlations, and the JSON for the site
- `data/archive/`: OpenAI incident archive and NVD cache, committed by the workflow
- `site/`: the static website (Plotly)
