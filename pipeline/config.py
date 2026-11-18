"""Sources and settings. Every number on the site comes from one of these."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
ARCHIVE = ROOT / "data" / "archive"
OUT = ROOT / "site" / "data"

# Analysis window: Ramp's series starts Jan 2023, which also skips the
# KEV catalogue's 2021-22 backfill of old vulnerabilities.
START_MONTH = "2023-01"

USER_AGENT = "ai-adoption-signals (GitHub portfolio project; contact via repo issues)"

# --- AI adoption --------------------------------------------------------
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
RAMP_SERIES = {
    "RAMPAIALL": "All businesses",
    "RAMPAISMB": "Small businesses",
    "RAMPAIENTERPRISE": "Large businesses",
}
BTOS_NATIONAL_XLSX = "https://www.census.gov/hfp/btos/downloads/National.xlsx"

# --- Cyber ----------------------------------------------------------------
KEV_JSON = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
NVD_API = "https://services.nvd.nist.gov/rest/json/cves/2.0"
# Seconds between NVD calls: public limit is 5 per 30 s, 50 per 30 s with a key.
NVD_DELAY_NO_KEY = 6.5
NVD_DELAY_WITH_KEY = 0.7

# Phrases that identify vulnerabilities in AI / machine-learning software.
# Each is sent to NVD's keywordSearch (matches the CVE description) and the
# results are de-duplicated by CVE ID.
AI_KEYWORDS = [
    "large language model",
    "LLM",
    "prompt injection",
    "LangChain",
    "Langflow",
    "LlamaIndex",
    "Ollama",
    "vLLM",
    "llama.cpp",
    "Open WebUI",
    "AnythingLLM",
    "Flowise",
    "Gradio",
    "MLflow",
    "ComfyUI",
    "Hugging Face",
    "PyTorch",
    "TensorFlow",
    "Triton Inference Server",
    "Copilot",
    "Model Context Protocol",
]
# Same idea for the KEV catalogue (vendor / product / name fields).
AI_KEV_PATTERN = (
    r"\b(langflow|langchain|llamaindex|ollama|vllm|open webui|anythingllm|flowise|"
    r"gradio|mlflow|comfyui|hugging ?face|pytorch|tensorflow|triton|copilot|ray|"
    r"openai|llm|model context protocol|mcp)\b"
)

# --- Service reliability -----------------------------------------------------
# Atlassian Statuspage sites expose full history at /history.json?page=N
STATUSPAGES = {
    "claude": {"label": "Claude (Anthropic)", "url": "https://status.claude.com"},
    "github": {"label": "GitHub", "url": "https://www.githubstatus.com", "focus": "Copilot"},
}
# OpenAI's status page only serves ~3 months, so we keep our own archive.
OPENAI_RSS = "https://status.openai.com/history.rss"

# --- Internet outages (needs a free token in the CLOUDFLARE_API_TOKEN secret) --
CF_OUTAGES = "https://api.cloudflare.com/client/v4/radar/annotations/outages"

# Correlation reading guide (absolute Spearman rho on month-to-month changes).
RHO_BANDS = [(0.1, "none"), (0.3, "weak"), (0.5, "moderate"), (1.01, "strong")]
PERMUTATIONS = 5000
