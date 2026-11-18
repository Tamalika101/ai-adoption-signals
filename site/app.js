"use strict";

const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const S = () => [css("--s1"), css("--s2"), css("--s3")];
const fmt = (n, d = 0) => (n == null ? "–" : Number(n).toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d }));
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const monthName = (m) => new Date(m + "-01T00:00:00").toLocaleString("en-US", { month: "short", year: "numeric" });

function layout(extra = {}) {
  return {
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "Inter, system-ui, sans-serif", size: 13, color: css("--ink-2") },
    margin: { l: 56, r: 16, t: 78, b: 44 },
    hovermode: "x unified",
    hoverlabel: { bgcolor: css("--surface"), bordercolor: css("--rule"), font: { color: css("--ink") } },
    xaxis: { gridcolor: "rgba(0,0,0,0)", linecolor: css("--rule"), tickfont: { color: css("--ink-3") } },
    yaxis: { gridcolor: css("--rule"), zeroline: false, tickfont: { color: css("--ink-3") }, rangemode: "tozero" },
    legend: { orientation: "h", y: 1.02, yanchor: "bottom", x: 0, font: { size: 12 } },
    title: { font: { family: "Fraunces, Georgia, serif", size: 17, color: css("--ink") }, x: 0, xanchor: "left", y: 0.97, yanchor: "top", pad: { l: 4 } },
    ...extra,
  };
}
const CFG = { displayModeBar: false, responsive: true };

function line(recs, name, color, opts = {}) {
  return { x: recs.map((r) => r.month ?? r.x), y: recs.map((r) => r.value ?? r.y), name, type: "scatter", mode: "lines",
    line: { color, width: 2, shape: "linear" }, hovertemplate: `%{y:.${opts.d ?? 1}f}${opts.suffix ?? ""}<extra>${esc(name)}</extra>`, ...opts.trace };
}
function bars(recs, name, color, opts = {}) {
  return { x: recs.map((r) => r.month), y: recs.map((r) => r.value), name, type: "bar",
    marker: { color, line: { width: 0 } }, hovertemplate: `%{y:,.0f}<extra>${esc(name)}</extra>`, ...opts.trace };
}
function plot(id, traces, title, extra = {}) {
  const el = document.getElementById(id);
  if (!el) return;
  Plotly.newPlot(el, traces, layout({ title: { ...layout().title, text: title }, bargap: 0.25, ...extra }), CFG);
}

async function main() {
  let D;
  try {
    D = await fetch("data/site.json", { cache: "no-cache" }).then((r) => r.json());
  } catch (e) {
    document.getElementById("verdict").textContent = "The data file could not be loaded. Please try again later.";
    return;
  }
  const M = D.metrics, L = D.labels, colors = S();
  document.getElementById("updated").textContent = `Data through ${monthName(D.through)} · refreshed ${D.generated}`;

  // ---- headline stats
  const ramp = D.adoption.ramp.RAMPAIALL || [];
  const rampLast = ramp[ramp.length - 1];
  const rampYearAgo = ramp[ramp.length - 13];
  const btos = (D.adoption.btos || []).filter((r) => r.kind === "Any business function");
  const btosLast = btos[btos.length - 1];
  const kevYear = (M.kev_added || []).filter((r) => r.month.startsWith(D.through.slice(0, 4))).reduce((a, r) => a + (r.value || 0), 0);
  const stats = [
    rampLast && [`${fmt(rampLast.value, 1)}%`, `of US businesses on Ramp paid for AI in ${monthName(rampLast.month)}` + (rampYearAgo ? ` (${fmt(rampYearAgo.value, 1)}% a year earlier)` : "")],
    btosLast && [`${fmt(btosLast.value, 1)}%`, `of US employers used AI in the two weeks to ${new Date(btosLast.end).toLocaleDateString("en-US", { month: "short", day: "numeric" })} (Census)`],
    [fmt(kevYear), `software flaws newly confirmed as exploited, Jan–${monthName(D.through).split(" ")[0]} ${D.through.slice(0, 4)}`],
    D.ai_cves && D.ai_cves.total != null && [fmt(D.ai_cves.total), "vulnerabilities in AI software published since Jan 2023"],
  ].filter(Boolean);
  document.getElementById("stats").innerHTML = stats.map(([b, s]) => `<div class="stat"><b>${b}</b><span>${s}</span></div>`).join("");

  scorecard(D);
  adoption(D, colors);
  exploited(D, colors);
  aiSoftware(D, colors);
  reliability(D, colors);
  internet(D, colors);
  sources(D);
}

const GROUPS = [
  ["Cyber attacks", ["kev_added", "kev_fast_share", "kev_median_lag", "kev_ransomware_share"]],
  ["Flaws in AI software", ["ai_cves", "ai_cves_per_1000"]],
  ["AI service disruptions", ["claude_incidents", "claude_major", "github_incidents", "github_major", "github_focus", "openai_incidents"]],
  ["Internet outages", ["internet_outages", "internet_outages_cyber"]],
];

function scorecard(D) {
  const rows = D.correlations.filter((c) => c.driver === "ramp");
  const byMetric = Object.fromEntries(rows.map((c) => [c.metric, c]));
  const btos = Object.fromEntries(D.correlations.filter((c) => c.driver === "btos").map((c) => [c.metric, c]));
  let html = `<thead><tr><th>Measure</th><th class="num">Months</th><th class="num">ρ levels</th><th class="num">ρ changes</th><th class="num">p</th><th>Reading (Ramp)</th><th>Reading (Census)</th></tr></thead><tbody>`;
  for (const [g, keys] of GROUPS) {
    const present = keys.filter((k) => byMetric[k]);
    if (!present.length) continue;
    html += `<tr class="group"><td colspan="7">${g}</td></tr>`;
    for (const k of present) {
      const c = byMetric[k], b = btos[k];
      html += `<tr><td>${esc(c.metric_label)}</td><td class="num">${c.n_months}</td><td class="num">${fmt(c.level_rho, 2)}</td>
        <td class="num">${fmt(c.change_rho, 2)}</td><td class="num">${c.p_value == null ? "–" : c.p_value < 0.001 ? "&lt;0.001" : fmt(c.p_value, 3)}</td>
        <td>${verdict(c.reading)}</td><td>${b ? verdict(b.reading) + ` <span class="note">(${b.n_months} mo)</span>` : "–"}</td></tr>`;
    }
  }
  document.getElementById("scorecard").innerHTML = html + "</tbody>";

  const tested = rows.filter((c) => c.change_rho != null);
  const linked = tested.filter((c) => c.reading.includes("link") && !c.reading.startsWith("no"));
  const trendy = tested.filter((c) => Math.abs(c.level_rho) >= 0.5 && c.reading === "no reliable link");
  let v = `<b>${linked.length} of ${tested.length}</b> measures show a reliable month-to-month link with AI adoption (Ramp).`;
  if (linked.length) v += ` Linked: ${linked.map((c) => `${esc(c.metric_label.toLowerCase())} (ρ ${fmt(c.change_rho, 2)})`).join("; ")}.`;
  if (trendy.length) v += ` ${linked.length ? "Another" : "Yet"} ${trendy.length} look strongly linked if you only compare the raw trend lines (|ρ| ≥ 0.5 in levels) but not once you compare the changes. That gap is the classic spurious correlation.`;
  document.getElementById("verdict").innerHTML = v;
}
function verdict(r) {
  const link = r && r.includes("link") && !r.startsWith("no");
  return `<span class="verdict ${link ? "link" : "nolink"}">${esc(r)}</span>`;
}

function adoption(D, c) {
  const labels = D.adoption.ramp_labels;
  const traces = Object.keys(labels).filter((k) => D.adoption.ramp[k]).map((k, i) => line(D.adoption.ramp[k], labels[k], c[i], { suffix: "%" }));
  plot("c-ramp", traces, "Share of US businesses paying for AI tools (Ramp, monthly)", { yaxis: { ...layout().yaxis, ticksuffix: "%" } });
  const b = (D.adoption.btos || []).filter((r) => r.kind === "Any business function");
  if (b.length) {
    plot("c-btos", [line(b.map((r) => ({ x: r.end, y: r.value })), "Used AI in the last two weeks", c[0], { suffix: "%", trace: { mode: "lines+markers", marker: { size: 8 } } })],
      "Share of US employers using AI (Census, every two weeks)", { yaxis: { ...layout().yaxis, ticksuffix: "%" }, showlegend: false });
    document.getElementById("btos-note").textContent = `Census series starts ${new Date(b[0].end).toLocaleDateString("en-US", { month: "long", year: "numeric" })}, when the question was broadened to AI use in any business function. Earlier figures used a narrower question and are not comparable.`;
  }
}

function exploited(D, c) {
  const M = D.metrics;
  if (M.kev_added) plot("c-kev", [bars(M.kev_added, "Newly confirmed exploited", c[0])], "Vulnerabilities added to CISA's exploited list, per month", { showlegend: false });
  const q = D.kev_quarterly || [];
  if (q.length) {
    plot("c-speed", [
      { x: q.map((r) => r.quarter), y: q.map((r) => r.within_7d), name: "Within 7 days of disclosure", type: "scatter", mode: "lines+markers", line: { color: c[1], width: 2 }, marker: { size: 8 }, hovertemplate: "%{y:.0f}%<extra>within 7 days</extra>" },
      { x: q.map((r) => r.quarter), y: q.map((r) => r.within_30d), name: "Within 30 days", type: "scatter", mode: "lines+markers", line: { color: c[0], width: 2 }, marker: { size: 8 }, hovertemplate: "%{y:.0f}%<extra>within 30 days</extra>" },
    ], "Share of newly listed flaws confirmed exploited soon after going public (by quarter)", { yaxis: { ...layout().yaxis, ticksuffix: "%" } });
  }
  const ai = D.kev_ai || [];
  document.getElementById("kev-ai").innerHTML = ai.length
    ? `<thead><tr><th>Added</th><th>CVE</th><th>Product</th><th>What it is</th><th>Ransomware</th></tr></thead><tbody>` +
      ai.map((r) => `<tr><td class="num">${r.dateAdded}</td><td><a href="https://nvd.nist.gov/vuln/detail/${esc(r.cveID)}" target="_blank" rel="noopener">${esc(r.cveID)}</a></td><td>${esc(r.vendorProject)} ${esc(r.product)}</td><td>${esc(r.vulnerabilityName)}</td><td>${esc(r.knownRansomwareCampaignUse)}</td></tr>`).join("") + "</tbody>"
    : `<tbody><tr><td>No AI-software entries found in the catalogue.</td></tr></tbody>`;
}

function aiSoftware(D, c) {
  const M = D.metrics;
  if (!M.ai_cves) {
    document.getElementById("c-aicve").outerHTML = `<p class="pending">Vulnerability database data is not available in this build.</p>`;
    return;
  }
  plot("c-aicve", [bars(M.ai_cves, "AI-software CVEs", c[0])], "New vulnerabilities in AI software, per month", { showlegend: false });
  plot("c-aishare", [line(M.ai_cves_per_1000, "per 1,000 new CVEs", c[1], { d: 1 })], "…per 1,000 of all new vulnerabilities", { showlegend: false });
  const kw = Object.entries(D.ai_cves.by_keyword || {}).filter(([, n]) => n > 0).sort((a, b) => a[1] - b[1]);
  plot("c-kw", [{ type: "bar", orientation: "h", y: kw.map((k) => k[0]), x: kw.map((k) => k[1]), marker: { color: c[0] }, hovertemplate: "%{x:,} CVEs<extra>%{y}</extra>" }],
    "Which AI software? (CVEs naming it)", { hovermode: "closest", margin: { l: 150, r: 16, t: 44, b: 32 }, yaxis: { automargin: true, tickfont: { color: css("--ink-2") } }, xaxis: { gridcolor: css("--rule") }, showlegend: false });
  document.getElementById("ai-top").innerHTML = (D.ai_cves.top || []).slice(0, 8).map((r) =>
    `<li><b><a href="https://nvd.nist.gov/vuln/detail/${esc(r.id)}" target="_blank" rel="noopener">${esc(r.id)}</a></b> · score ${fmt(r.score, 1)} · ${esc(r.published)}<br>${esc(r.description.slice(0, 180))}${r.description.length > 180 ? "…" : ""}</li>`).join("");
}

function reliability(D, c) {
  const M = D.metrics, L = D.labels;
  const keys = ["claude_incidents", "github_incidents", "github_major", "github_focus"].filter((k) => M[k]);
  if (!keys.length) { document.getElementById("c-status").outerHTML = `<p class="pending">Status page data is not available in this build.</p>`; return; }
  plot("c-status", keys.map((k, i) => line(M[k], L[k], c[i], { d: 0 })), "Incidents reported on official status pages, per month");
  const oa = M.openai_incidents;
  document.getElementById("status-note").textContent = oa && oa.length >= 8
    ? `OpenAI incidents are included in the table from our own archive (${oa.length} months).`
    : `OpenAI's status page only shows about three months of history, so this site keeps its own weekly archive (${oa ? oa.length : 0} full months so far). OpenAI joins the comparison once it reaches eight months.`;
}

function internet(D, c) {
  const M = D.metrics, body = document.getElementById("internet-body");
  if (!M.internet_outages) {
    body.innerHTML = `<p class="pending">Coming soon. This section uses Cloudflare Radar's public outage records, which need a free access key. It will appear automatically once the key is added.</p>`;
    return;
  }
  body.innerHTML = `<p>Cloudflare, which carries a large share of web traffic, logs significant internet disruptions worldwide with their likely cause: power cuts, cable damage, government shutdowns, cyberattacks and more.</p><div class="chart" id="c-cf"></div><div class="chart small" id="c-causes"></div>`;
  plot("c-cf", [bars(M.internet_outages, "All outages", c[0]), bars(M.internet_outages_cyber, "Caused by cyberattacks", c[1])], "Internet outages logged by Cloudflare Radar, per month", { barmode: "overlay" });
  const cs = Object.entries(D.outage_causes || {}).sort((a, b) => a[1] - b[1]);
  plot("c-causes", [{ type: "bar", orientation: "h", y: cs.map((x) => x[0].replace(/_/g, " ").toLowerCase()), x: cs.map((x) => x[1]), marker: { color: c[0] }, hovertemplate: "%{x}<extra>%{y}</extra>" }],
    "Outages by cause since 2023", { hovermode: "closest", margin: { l: 170, r: 16, t: 44, b: 32 }, showlegend: false });
}

function sources(D) {
  const list = [
    ["Ramp AI Index", "https://ramp.com/data/ai-index", "via FRED series RAMPAIALL, RAMPAISMB, RAMPAIENTERPRISE (St. Louis Fed)"],
    ["Census Bureau, Business Trends and Outlook Survey", "https://www.census.gov/hfp/btos/data_downloads", "national estimates, National.xlsx"],
    ["CISA Known Exploited Vulnerabilities Catalog", "https://www.cisa.gov/known-exploited-vulnerabilities-catalog", "JSON feed"],
    ["NIST National Vulnerability Database", "https://nvd.nist.gov/developers/vulnerabilities", "CVE API 2.0 (publication dates, keyword search, monthly totals)"],
    ["Claude status page", "https://status.claude.com/history", "incident history"],
    ["GitHub status page", "https://www.githubstatus.com/history", "incident history"],
    ["OpenAI status page", "https://status.openai.com/history", "RSS feed, archived weekly by this site"],
    ["Cloudflare Radar Outage Center", "https://radar.cloudflare.com/outage-center", "outage annotations API"],
  ];
  const ok = D.sources_ok || {};
  const missing = Object.entries(ok).filter(([, v]) => !v).map(([k]) => k);
  document.getElementById("sources").innerHTML = list.map(([n, u, d]) => `<li><a href="${u}" target="_blank" rel="noopener">${n}</a>: ${d}</li>`).join("") +
    (missing.length ? `<li><b>Not available in this build:</b> ${missing.map(esc).join(", ")}</li>` : "");
}

main();
