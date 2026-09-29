"""
Mode A: OpenRouter engine with SPECIFIC models (no random router).

OPENROUTER_MODELS in .env is a comma separated list, e.g.
  anthropic/<claude-model>,google/<gemini-model>,openai/<gpt-model>,x-ai/<grok-model>,deepseek/<deepseek-model>
The models are tried left to right; the first one that returns a valid answer wins.
OpenRouter speaks the OpenAI-compatible /chat/completions API, so plain HTTPS
via `requests` is enough.
"""

import json
import re
import logging
import requests

import config
from schema import build_schema
from prompt_builder import build_prompt

logger = logging.getLogger(__name__)

_REQUIRED_KEYS = ("material", "predicted_properties")
_PROP_KEYS = ("moisture_pct", "fat_pct", "ph", "respiration_rate",
              "storage_temp_c", "relative_humidity_pct")


def has_configured_keys() -> bool:
    return bool(config.OPENROUTER_API_KEY and config.OPENROUTER_MODELS)


def _extract_json(text: str) -> dict:
    """Some models wrap the JSON in ``` fences or add a sentence around it."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


def _post(payload: dict) -> requests.Response:
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://127.0.0.1:5000",
        "X-Title": "Food Packaging Recommender",
    }
    return requests.post(
        f"{config.OPENROUTER_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=(10, config.OPENROUTER_TIMEOUT_SECONDS),
    )


def _call_one_model(model: str, prompt: str, schema: dict) -> dict:
    payload = {
        "model": model,
        "temperature": 0.2,
        "max_tokens": 3000,
        "messages": [
            {"role": "system", "content":
                "You are a JSON API. Reply with exactly ONE valid JSON object and nothing else "
                "(no markdown, no explanation)."},
            {"role": "user", "content":
                prompt + "\n\nRETURN A JSON OBJECT MATCHING THIS JSON SCHEMA:\n" + json.dumps(schema)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "packaging_recommendation", "strict": False, "schema": schema},
        },
    }

    resp = _post(payload)
    if resp.status_code in (400, 404, 422) and "response_format" in resp.text:
        logger.warning("%s: no response_format support, retrying with prompt-only JSON", model)
        payload.pop("response_format")
        resp = _post(payload)

    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:250]}")

    body = resp.json()
    if body.get("error"):
        raise RuntimeError(f"API error: {str(body['error'])[:250]}")

    content = body["choices"][0]["message"].get("content")
    parsed = _extract_json(content)

    missing = [k for k in _REQUIRED_KEYS if k not in parsed]
    if missing:
        raise ValueError(f"missing fields: {missing}")

    props = parsed["predicted_properties"]
    for k in _PROP_KEYS:                     # numbers sometimes come back as strings
        try:
            props[k] = float(props[k])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"predicted_properties.{k} missing or not a number")

    parsed["source"] = "openrouter_ai"
    parsed["ai_model"] = body.get("model") or model
    return parsed


def call_openrouter(data: dict, available_shapes: list = None) -> dict:
    prompt = build_prompt(data, available_shapes)
    schema = build_schema(available_shapes)

    last_error = None
    for model in config.OPENROUTER_MODELS:
        try:
            result = _call_one_model(model, prompt, schema)
            logger.info("OpenRouter model %s answered", model)
            return result
        except Exception as e:
            logger.warning("OpenRouter model %s failed (%s) - trying next model", model, e)
            last_error = e
    raise last_error or RuntimeError("No OpenRouter model configured")


call = call_openrouter
