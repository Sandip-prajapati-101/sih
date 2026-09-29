"""
AI-Based Intelligent Food Packaging Material Recommendation System
SIH PS-26236 - Flask Backend (entry point)

Flow:
  Frontend --> POST /api/recommend --> Flask
    --> OpenRouter (specific models) or Gemini (predicts properties + recommends)
    --> if every AI provider fails --> offline rule engine
  Flask --> deterministic packaging-structure logic (offline_engine.resolve_layers)
         --> picks the matching 3D file(s) from static/models/<budget>/<shape>/...
  Flask --> JSON (with one or two "layers") --> Frontend renders result + 3D model(s)
"""

import os
import logging
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

import config
import gemini_engine
import openrouter_engine
import offline_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "static", "models")   # put your 3D files here

app = Flask(__name__)  # auto-serves the "static/" folder at /static/...
CORS(app)

BUDGET_FOLDERS = ("low", "medium", "high")


def list_models() -> dict:
    """
    Scans static/models and returns {budget: {shape: [relative_paths...]}}.

    Preferred layout (budget-aware, what this app expects going forward):
        static/models/<low|medium|high>/<shape>/model.glb
        static/models/<low|medium|high>/<shape>/scene.gltf (+ .bin, textures/...)

    Also supported for backwards compatibility - a flat folder with no budget
    split, filed under the special budget key "any":
        static/models/<shape>/model.glb
    """
    tree: dict = {}
    if not os.path.isdir(MODELS_DIR):
        return tree
    for root, _dirs, files in os.walk(MODELS_DIR):
        for f in files:
            if not f.lower().endswith((".glb", ".gltf")):
                continue
            rel = os.path.relpath(os.path.join(root, f), MODELS_DIR).replace(os.sep, "/")
            parts = rel.split("/")
            if len(parts) >= 3 and parts[0] in BUDGET_FOLDERS:
                budget, shape = parts[0], parts[1]
            elif len(parts) >= 2:
                budget, shape = "any", parts[0]
            else:
                continue  # a loose file directly in static/models/ - shape unknown, skip
            tree.setdefault(budget, {}).setdefault(shape, []).append(rel)
    for shapes in tree.values():
        for files in shapes.values():
            files.sort()
    return tree


ENGINES = {"openrouter": openrouter_engine, "gemini": gemini_engine}


def run_ai(data: dict, model_files: list) -> dict:
    """Try each configured AI provider in AI_PROVIDER_ORDER; raise if none works.
    model_files is only used to tell the AI which packaging_shape values make
    sense to describe in words - the actual 3D file is always chosen afterwards
    by attach_model_layers(), never by the AI."""
    tried = 0
    last_error = None
    for name in config.AI_PROVIDER_ORDER:
        engine = ENGINES.get(name)
        if engine is None or not engine.has_configured_keys():
            continue
        tried += 1
        try:
            result = engine.call(data, model_files)
            logger.info("Served via %s AI", name)
            return result
        except Exception as e:
            logger.warning("%s failed (%s)", name, e)
            last_error = e
    if tried == 0:
        raise RuntimeError("No AI provider configured (add a key in .env)")
    raise last_error


def attach_model_layers(result: dict, models_tree: dict, data: dict) -> dict:
    """Authoritative packaging structure for the 3D preview: 1-2 layers, decided
    purely from packet weight / category / respiration - the same for every
    request regardless of which AI (or the offline engine) wrote the text."""
    budget = (data.get("budget") or "medium").lower()
    if budget not in BUDGET_FOLDERS:
        budget = "medium"

    # The AI decides the packaging structure itself (packaging_layers in its JSON
    # answer). Only fall back to the deterministic weight-tier rule if that is
    # missing or malformed (e.g. offline mode, or a model that ignored the field).
    layers = offline_engine.validate_layers(result.get("packaging_layers"))
    if layers is None:
        logger.info("No valid packaging_layers from AI - using weight-tier fallback")
        layers = offline_engine.resolve_layers(result, data)

    layer_info = []
    for i, shape in enumerate(layers):
        is_outer = (i == len(layers) - 1)
        budget_used, rel_file = offline_engine.pick_model(models_tree, budget, shape)
        label = offline_engine.LAYER_LABELS.get(shape, shape)
        if not is_outer:
            label += " (inner liner)"
        layer_info.append({
            "shape": shape,
            "label": label,
            "budget_requested": budget,
            "budget_used": budget_used,
            "model_file": rel_file,
            "model_url": f"static/models/{rel_file}" if rel_file else None,
        })

    result["packaging_shape"] = layers[-1]      # outer/most visible container, kept for old clients
    result["packaging_layers"] = layers
    result["layers"] = layer_info
    result["model_file"] = layer_info[0]["model_file"]
    result["model_url"] = layer_info[0]["model_url"]
    return result


@app.route("/")
def serve_index():
    # Served over http:// (not file://) so the Three.js ES modules can load.
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/api/recommend", methods=["POST"])
def recommend():
    data = request.get_json(force=True, silent=True) or {}
    logger.info("Incoming request: %s", data)
    models_tree = list_models()
    model_shapes_available = sorted({s for shapes in models_tree.values() for s in shapes})

    try:
        result = run_ai(data, model_shapes_available)
    except Exception as e:
        logger.warning("All AI providers failed (%s) - falling back to offline engine", e)
        result = offline_engine.offline_rule_engine(data)

    return jsonify(attach_model_layers(result, models_tree, data))


@app.route("/api/health", methods=["GET"])
def health():
    models_tree = list_models()
    flat = sorted(f for shapes in models_tree.values() for files in shapes.values() for f in files)
    return jsonify({
        "status": "ok",
        "provider_order": config.AI_PROVIDER_ORDER,
        "openrouter_key_loaded": openrouter_engine.has_configured_keys(),
        "openrouter_models": config.OPENROUTER_MODELS,
        "gemini_keys_loaded": len(config.GEMINI_API_KEYS),
        "models_found": flat,
        "budgets_found": sorted(models_tree.keys()),
    })


if __name__ == "__main__":
    # use_reloader=False: avoids a crash when files change while a request is in flight.
    app.run(debug=True, use_reloader=False, port=config.FLASK_PORT)
