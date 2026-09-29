"""
Mode A: Gemini AI Engine.

Every configured API key (separate free-tier quota pools) is fired in parallel
and the FIRST valid answer wins. If all fail or time out, app.py falls back to
the offline rule engine.
"""

import json
import logging
import concurrent.futures
from google import genai
from google.genai import types

import config
from schema import build_schema
from prompt_builder import build_prompt

logger = logging.getLogger(__name__)

# attempts=1 -> one real HTTP call per key (no hidden SDK retries eating quota)
_no_retry_http_options = types.HttpOptions(
    retry_options=types.HttpRetryOptions(attempts=1)
)

_gemini_clients = [
    genai.Client(api_key=key, http_options=_no_retry_http_options)
    for key in config.GEMINI_API_KEYS
]

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)

_REQUIRED_KEYS = ("material", "predicted_properties")


def has_configured_keys() -> bool:
    return bool(_gemini_clients)


_RETRY_NEXT_MODEL = ("503", "UNAVAILABLE", "overloaded", "404", "NOT_FOUND")


def _call_gemini_with_client(client, prompt: str, schema: dict) -> dict:
    """One key: try each model in GEMINI_MODELS until one answers."""
    cfg = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=schema,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    response, used_model, last_error = None, None, None
    for model in config.GEMINI_MODELS:
        try:
            response = client.models.generate_content(model=model, contents=prompt, config=cfg)
            used_model = model
            break
        except Exception as e:
            last_error = e
            if any(t in str(e) for t in _RETRY_NEXT_MODEL):
                logger.warning("Model %s unavailable (%s) - trying next model", model, str(e)[:80])
                continue
            raise
    if response is None:
        raise last_error

    text = (response.text or "").strip()
    if text.startswith("```"):  # safety: strip accidental markdown fences
        text = text.strip("`").removeprefix("json").strip()
    parsed = json.loads(text)
    missing = [k for k in _REQUIRED_KEYS if k not in parsed]
    if missing:
        raise ValueError(f"AI response missing fields: {missing}")
    parsed["source"] = "gemini_ai"
    parsed["ai_model"] = used_model
    return parsed


def call_gemini(data: dict, available_shapes: list = None) -> dict:
    prompt = build_prompt(data, available_shapes)
    schema = build_schema(available_shapes)

    futures = {
        _executor.submit(_call_gemini_with_client, client, prompt, schema): i
        for i, client in enumerate(_gemini_clients, start=1)
    }

    errors = []
    try:
        for future in concurrent.futures.as_completed(futures, timeout=config.GEMINI_TIMEOUT_SECONDS):
            key_num = futures[future]
            try:
                result = future.result()
                logger.info("Gemini key #%d succeeded (first to respond)", key_num)
                return result
            except Exception as e:
                logger.warning("Gemini key #%d failed (%s)", key_num, e)
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    logger.warning("Key #%d: quota exhausted (429)", key_num)
                errors.append(e)
        raise errors[-1] if errors else RuntimeError("All Gemini keys failed")
    except concurrent.futures.TimeoutError:
        logger.warning("No Gemini key responded within %ds", config.GEMINI_TIMEOUT_SECONDS)
        raise TimeoutError(f"No key responded within {config.GEMINI_TIMEOUT_SECONDS}s")


call = call_gemini
