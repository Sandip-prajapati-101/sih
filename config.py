"""
Configuration for the Food Packaging Recommendation backend.
API keys are read from the ".env" file (or environment variables) - they are
NOT written in code. Keep .env private and never push it to GitHub.
"""

import os

_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

try:
    from dotenv import load_dotenv
    load_dotenv(_ENV_PATH)
except ImportError:
    # python-dotenv not installed -> read the .env file ourselves (KEY=VALUE lines)
    if os.path.isfile(_ENV_PATH):
        with open(_ENV_PATH, encoding="utf-8-sig") as _f:
            for _line in _f:
                _line = _line.strip()
                if not _line or _line.startswith("#") or "=" not in _line:
                    continue
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))


def _clean(v):
    v = (v or "").strip()
    return "" if v.startswith("PASTE_") else v


# ---------------- Provider order ----------------
# Providers are tried left to right; if all fail -> offline rule engine.
AI_PROVIDER_ORDER = [
    p.strip().lower()
    for p in os.environ.get("AI_PROVIDER_ORDER", "openrouter,gemini").split(",")
    if p.strip()
]

# ---------------- OpenRouter (or any OpenAI-compatible router) ----------------
OPENROUTER_API_KEY = _clean(os.environ.get("OPENROUTER_API_KEY"))
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip().rstrip("/")
OPENROUTER_TIMEOUT_SECONDS = int(os.environ.get("OPENROUTER_TIMEOUT_SECONDS", "60"))

# Specific models, tried LEFT TO RIGHT (comma separated), e.g. one Claude, one Gemini,
# one GPT, one Grok, one DeepSeek. Get exact slugs with:  python list_openrouter_models.py
_models_raw = os.environ.get("OPENROUTER_MODELS") or os.environ.get("OPENROUTER_MODEL") or ""
OPENROUTER_MODELS = []
for _m in (x.strip() for x in _models_raw.split(",")):
    if not _m or _m.startswith("PASTE_"):
        continue
    if _m.startswith("openrouter/"):      # openrouter/free, openrouter/auto = random model -> not allowed
        continue
    OPENROUTER_MODELS.append(_m)

# ---------------- Gemini (optional, up to 4 keys fired in parallel) ----------------
GEMINI_API_KEYS = [
    k for k in (_clean(os.environ.get(f"GEMINI_API_KEY_{i}")) for i in range(1, 5)) if k
]
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
# If the main model is overloaded (503) or missing (404), the next ones are tried automatically.
GEMINI_MODELS = [GEMINI_MODEL] + [
    m for m in ("gemini-2.5-flash", "gemini-3.5-flash") if m != GEMINI_MODEL
]
GEMINI_TIMEOUT_SECONDS = 40

FLASK_PORT = 5000
