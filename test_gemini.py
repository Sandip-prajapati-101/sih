"""
Run:  python test_gemini.py
Finds out exactly WHY Gemini fails (network, key, model name or SDK).
Never prints your API key.
"""
import json
import urllib.request
import urllib.error

import config

if not config.GEMINI_API_KEYS:
    raise SystemExit("No key loaded from .env")
KEY = config.GEMINI_API_KEYS[0]
print("Keys loaded:", len(config.GEMINI_API_KEYS), "| model in config:", config.GEMINI_MODEL)

print("\n[1] urllib -> list models (checks key + real model names)")
try:
    req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
        headers={"x-goog-api-key": KEY},
    )
    data = json.load(urllib.request.urlopen(req, timeout=20))
    names = [m["name"].replace("models/", "") for m in data.get("models", [])]
    flash = [n for n in names if "flash" in n]
    print("OK. Flash models available:", flash)
    print("Your config model exists:", config.GEMINI_MODEL in names)
except urllib.error.HTTPError as e:
    print("HTTP error:", e.code, e.read()[:300])
except Exception as e:
    print("FAILED:", type(e).__name__, e)

print("\n[2] httpx (what the Gemini SDK uses under the hood)")
try:
    import httpx
    r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models",
                  headers={"x-goog-api-key": KEY}, timeout=20)
    print("OK status:", r.status_code, "| httpx", httpx.__version__)
except Exception as e:
    print("FAILED:", type(e).__name__, e)

print("\n[3] google-genai SDK simple call")
try:
    from google import genai
    client = genai.Client(api_key=KEY)
    out = client.models.generate_content(model=config.GEMINI_MODEL, contents="Reply with the word OK")
    print("OK:", out.text)
except Exception as e:
    print("FAILED:", type(e).__name__, str(e)[:400])
