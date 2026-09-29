"""
Run:  python list_openrouter_models.py
Prints the newest models of Claude / Gemini / GPT / Grok / DeepSeek on OpenRouter
with their EXACT slug and price, so you can paste them into OPENROUTER_MODELS in .env.
(No API key needed - the model list is public.)
"""
import json
import urllib.request

VENDORS = [
    ("anthropic", "Claude"),
    ("google", "Gemini"),
    ("openai", "GPT / ChatGPT"),
    ("x-ai", "Grok"),
    ("deepseek", "DeepSeek"),
]
PER_VENDOR = 8

req = urllib.request.Request("https://openrouter.ai/api/v1/models", headers={"User-Agent": "Mozilla/5.0"})
models = json.load(urllib.request.urlopen(req, timeout=30)).get("data", [])


def per_million(v):
    try:
        return float(v) * 1_000_000
    except (TypeError, ValueError):
        return None


for prefix, label in VENDORS:
    rows = [m for m in models if m["id"].startswith(prefix + "/")
            and ":free" not in m["id"] and ":" not in m["id"]]
    rows.sort(key=lambda m: m.get("created", 0), reverse=True)
    print("\n=== %s  (newest first) ===" % label)
    print("%-48s %-10s %-10s %s" % ("SLUG (paste this)", "IN $/1M", "OUT $/1M", "JSON-mode"))
    for m in rows[:PER_VENDOR]:
        p = m.get("pricing", {})
        pin, pout = per_million(p.get("prompt")), per_million(p.get("completion"))
        params = m.get("supported_parameters") or []
        js = "yes" if ("structured_outputs" in params or "response_format" in params) else "no"
        print("%-48s %-10s %-10s %s" % (
            m["id"],
            "%.2f" % pin if pin is not None else "?",
            "%.2f" % pout if pout is not None else "?",
            js,
        ))

print("\nPut 3-5 slugs in .env like:")
print("OPENROUTER_MODELS=slug_1,slug_2,slug_3")
