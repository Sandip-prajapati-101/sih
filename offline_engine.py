"""
Mode B: Offline Rule Engine + the deterministic packaging-STRUCTURE logic
(shape, weight tier, number of layers) that both the offline engine AND the
AI engines' results are passed through, so the 3D preview always matches the
real-world pack instead of trusting a random AI guess.
"""

# ---------------------------------------------------------------------------
# Typical values per category (used only when Gemini/OpenRouter are unavailable)
# ---------------------------------------------------------------------------
DEFAULT_PROPS = {
    "fruits": dict(moisture_pct=85, fat_pct=0.5, ph=4.5, respiration_rate=15, storage_temp_c=8,  relative_humidity_pct=90),
    "snacks": dict(moisture_pct=3,  fat_pct=30,  ph=6.5, respiration_rate=0,  storage_temp_c=25, relative_humidity_pct=50),
    "dairy":  dict(moisture_pct=87, fat_pct=3.5, ph=6.7, respiration_rate=0,  storage_temp_c=4,  relative_humidity_pct=85),
    "bakery": dict(moisture_pct=35, fat_pct=8,   ph=6.0, respiration_rate=0,  storage_temp_c=25, relative_humidity_pct=55),
    "other":  dict(moisture_pct=15, fat_pct=5,   ph=6.5, respiration_rate=0,  storage_temp_c=25, relative_humidity_pct=60),
}

CATEGORY_DEFAULT_SHAPE = {
    "fruits": "stand_up_pouch", "snacks": "flow_wrap", "dairy": "bottle",
    "bakery": "flow_wrap", "other": "cardboard_box",
}

# The 6 pack shapes the whole system understands. Folder names under
# static/models/<budget>/<shape>/ must use these exact codes.
ALL_SHAPES = ("stand_up_pouch", "flow_wrap", "bottle", "jar", "cardboard_box", "bulk_bag")

LAYER_LABELS = {
    "stand_up_pouch": "Stand-up pouch",
    "flow_wrap":      "Flow-wrap packet",
    "bottle":         "Bottle",
    "jar":            "Jar",
    "cardboard_box":  "Cardboard box / crate",
    "bulk_bag":       "Bulk bag / sack",
}

# keywords looked for inside legacy (no-budget-folder) file names, e.g. pouch.glb
SHAPE_KEYWORDS = {
    "stand_up_pouch": ["pouch", "standup", "stand_up", "stand-up"],
    "flow_wrap":      ["flow", "wrap", "pillow", "sachet", "chips", "packet"],
    "bottle":         ["bottle", "pet", "jug"],
    "jar":            ["jar", "tub", "container"],
    "cardboard_box":  ["box", "carton", "cardboard", "crate"],
    "bulk_bag":       ["bulk", "sack", "gunny", "jute", "bag"],
}

# words in the recommended material that reveal the pack type (used only when
# nothing else is available - the weight-tier rule below normally overrides this)
_TEXT_HINTS = [
    ("bulk_bag", ["bulk bag", "jute", "gunny", "woven sack", "woven bag", "hdpe sack"]),
    ("bottle", ["bottle", "jug", "rpet"]),
    ("jar", ["jar", "glass"]),
    ("cardboard_box", ["corrugated", "cardboard", "crate", "carton", " box"]),
    ("flow_wrap", ["flow-wrap", "flow wrap", "pillow", "metalized bopp", "metallized bopp"]),
    ("stand_up_pouch", ["pouch", "stand-up", "stand up", "sachet"]),
]

BULKY_PRODUCE = ("banana", "mango", "papaya", "pineapple", "melon", "cabbage",
                 "cauliflower", "pumpkin", "coconut", "jackfruit", "watermelon",
                 "kela", "keri", "kobi")

# packet weight tiers, in kg. Anything below CASE_MIN_KG is a normal retail pack;
# CASE_MIN_KG-BULK_MIN_KG is a "case" (box); BULK_MIN_KG and up is a "bulk" pack (sack).
CASE_MIN_KG = 5
BULK_MIN_KG = 15


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _to_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _packet_grams(data):
    w = _to_float(data.get("packetWeight"))
    return w * 1000 if (data.get("packetUnit") or "g") == "kg" else w


def _is_bulky_produce(data):
    name = (data.get("commodityName") or "").lower()
    return (data.get("foodCategory") or "").lower() == "fruits" and any(w in name for w in BULKY_PRODUCE)


def _is_respiring(result, data):
    """True for anything that needs a breathable inner layer: fresh produce,
    whether we know that from the category, the name, or the predicted respiration rate."""
    category = (data.get("foodCategory") or "").lower()
    if category == "fruits" or _is_bulky_produce(data):
        return True
    try:
        return _to_float((result or {}).get("predicted_properties", {}).get("respiration_rate")) > 0
    except (TypeError, AttributeError):
        return False


def _primary_shape(result: dict, data: dict) -> str:
    """The innermost / smallest pack shape for this commodity, ignoring weight."""
    shape = (result or {}).get("packaging_shape")
    if shape not in ALL_SHAPES:
        text = " " + " ".join(str((result or {}).get(k, "")) for k in ("material", "gas_filler")).lower()
        shape = next((s for s, words in _TEXT_HINTS if any(w in text for w in words)), None)
    if shape not in ALL_SHAPES:
        shape = CATEGORY_DEFAULT_SHAPE.get((data.get("foodCategory") or "other").lower(), "cardboard_box")
    return shape


def weight_tier(packet_kg: float) -> str:
    if packet_kg >= BULK_MIN_KG:
        return "bulk"
    if packet_kg >= CASE_MIN_KG:
        return "case"
    return "retail"


def validate_layers(raw) -> list:
    """Accept the AI's own "packaging_layers" only if it is a well-formed 1-2 item
    list of real shape codes; otherwise return None so the caller falls back to the
    deterministic weight-tier rule below."""
    if not isinstance(raw, list) or not (1 <= len(raw) <= 2):
        return None
    if not all(isinstance(s, str) and s in ALL_SHAPES for s in raw):
        return None
    return raw


def resolve_layers(result: dict, data: dict) -> list:
    """
    SAFETY-NET ONLY: used when the AI did not return a valid "packaging_layers", or
    when running in offline mode. The AI is asked to decide packaging_layers itself
    (see prompt_builder.py rule 8); this deterministic weight-tier rule exists purely
    so the 3D preview is never left broken if the AI's answer is missing/invalid.
    Returns an ordered list of 1-2 shape codes, innermost layer first.
    """
    packet_kg = _packet_grams(data) / 1000.0
    tier = weight_tier(packet_kg)
    inner = _primary_shape(result, data)
    respiring = _is_respiring(result, data)

    if tier == "retail":
        # whole/bulky produce, or ANY fresh produce >= 1 kg, is not sold in a small
        # pouch - it goes straight into a small ventilated carton (1 layer)
        if _is_bulky_produce(data) or ((data.get("foodCategory") or "").lower() == "fruits" and packet_kg >= 1):
            return ["cardboard_box"]
        return [inner]

    if tier == "case":
        # 5-15 kg: a case/crate. Respiring produce needs a breathable inner liner
        # in direct food contact, separate from the structural outer box.
        return [inner, "cardboard_box"] if respiring else ["cardboard_box"]

    # tier == "bulk" (>= 15 kg): a woven/jute/HDPE sack, never a box or pouch.
    return [inner, "bulk_bag"] if respiring else ["bulk_bag"]


# ---------------------------------------------------------------------------
# 3D file lookup: static/models/<budget>/<shape>/... (budget folder optional -
# a flat static/models/<shape>/... still works for anyone who hasn't split
# their files into low/medium/high yet)
# ---------------------------------------------------------------------------
def pick_model(models_tree: dict, budget: str, shape: str):
    """Returns (budget_used, relative_file_path) or (None, None) if nothing fits.
    Prefers an exact match for the requested budget tier, then falls back to the
    other tiers, then to a legacy flat folder, then to filename-keyword matching."""
    if not models_tree:
        return None, None

    search_order = [budget] + [b for b in ("medium", "low", "high", "any") if b != budget]
    for b in search_order:
        files = models_tree.get(b, {}).get(shape)
        if files:
            return b, files[0]

    # shape missing under any preferred tier -> any budget that happens to have it
    for b, shapes in models_tree.items():
        if shapes.get(shape):
            return b, shapes[shape][0]

    # last resort: filename keyword match anywhere (very old flat installs)
    all_files = [f for shapes in models_tree.values() for files in shapes.values() for f in files]
    for kw in SHAPE_KEYWORDS.get(shape, []):
        for f in all_files:
            if kw in f.lower():
                return None, f
    return None, None


# ---------------------------------------------------------------------------
# Mode B recommendation content (used only when every AI provider fails)
# ---------------------------------------------------------------------------
def offline_rule_engine(data: dict) -> dict:
    category = (data.get("foodCategory") or "other").lower()
    if category not in DEFAULT_PROPS:
        category = "other"
    storage_type = (data.get("storageType") or "ambient").lower()

    props = dict(DEFAULT_PROPS[category])
    if storage_type == "frozen":
        props["storage_temp_c"] = -18
    elif storage_type == "chilled":
        props["storage_temp_c"] = 4
    elif props["storage_temp_c"] < 15:
        props["storage_temp_c"] = 25

    if category == "fruits":
        result = {
            "material": "Micro-perforated LDPE (Low-Density Polyethylene)",
            "reasoning": "Micro-perforations allow controlled respiration/gas exchange, keeping fresh produce from suffocating or rotting early.",
            "otr_value": "3000-6000 cc/m2/day (micro-perforated)",
            "wvtr_value": "8-15 g/m2/day",
            "film_thickness_microns": "30-40 microns",
            "sealability": "Heat-sealable, seal strength ~15-20 N/15mm",
            "gas_permeability": "High O2/CO2 exchange via perforations to sustain respiration",
            "mechanical_strength": "Moderate tensile strength, adequate for light produce handling",
            "map_suitability": "Recommended (passive MAP via micro-perforation)",
            "map_gas_composition": "3-5% O2, 5-10% CO2, balance N2",
            "gas_filler": "None (breathable film with foam net cushioning)",
            "sustainable_option": "PLA (Polylactic Acid) compostable film",
            "packaging_shape": "stand_up_pouch",
            "shelf_life_prediction_days": "7-14 days",
            "cost_estimate": "Low - approx Rs 1-2 per unit",
            "qr_traceability_note": "Link QR to farm/harvest date, batch number, and cold-chain log",
        }
    elif category == "snacks":
        result = {
            "material": "Metalized BOPP (Biaxially Oriented Polypropylene)",
            "reasoning": "Excellent oxygen and moisture barrier, prevents oil oxidation and keeps fried snacks crisp.",
            "otr_value": "1-2 cc/m2/day",
            "wvtr_value": "0.5-1 g/m2/day",
            "film_thickness_microns": "18-25 microns",
            "sealability": "Heat-sealable flow-wrap, seal strength ~25-30 N/15mm",
            "gas_permeability": "Very low - protects oil from oxidative rancidity",
            "mechanical_strength": "High puncture resistance for distribution handling",
            "map_suitability": "Recommended",
            "map_gas_composition": "100% Nitrogen",
            "gas_filler": "100% Nitrogen gas flush",
            "sustainable_option": "PBAT-based compostable metalized film",
            "packaging_shape": "flow_wrap",
            "shelf_life_prediction_days": "90-180 days",
            "cost_estimate": "Medium - approx Rs 2-4 per unit",
            "qr_traceability_note": "Link QR to batch code, manufacturing date, and expiry",
        }
    elif category == "dairy":
        result = {
            "material": "Multilayer HDPE with EVOH barrier",
            "reasoning": "EVOH gives an excellent oxygen barrier to limit lipid oxidation; HDPE provides moisture protection and rigidity.",
            "otr_value": "0.5-1.5 cc/m2/day",
            "wvtr_value": "1-3 g/m2/day",
            "film_thickness_microns": "50-80 microns (bottle wall equivalent)",
            "sealability": "Induction-sealed cap, tamper-evident",
            "gas_permeability": "Low - protects against off-flavor development",
            "mechanical_strength": "High rigidity for stacking and cold-chain handling",
            "map_suitability": "Not typically required for sealed liquid containers",
            "map_gas_composition": "Not applicable",
            "gas_filler": "None (vacuum-sealed cap)",
            "sustainable_option": "rPET (recycled PET) bottle",
            "packaging_shape": "bottle",
            "shelf_life_prediction_days": "10-15 days (chilled)",
            "cost_estimate": "Medium - approx Rs 3-5 per unit",
            "qr_traceability_note": "Link QR to dairy source, batch, and cold-chain temperature log",
        }
    elif category == "bakery":
        result = {
            "material": "BOPP / PE laminate with anti-fog seal layer",
            "reasoning": "Moderate moisture barrier retains softness while limiting mould-favouring condensation for bakery goods.",
            "otr_value": "800-1500 cc/m2/day",
            "wvtr_value": "4-8 g/m2/day",
            "film_thickness_microns": "25-35 microns",
            "sealability": "Heat-sealable, seal strength ~15-20 N/15mm",
            "gas_permeability": "Moderate - allows limited moisture escape",
            "mechanical_strength": "Moderate puncture resistance for soft products",
            "map_suitability": "Optional for longer shelf life",
            "map_gas_composition": "Not applicable (or 30% CO2 / 70% N2 if MAP is used)",
            "gas_filler": "None",
            "sustainable_option": "PLA / paper-based laminate",
            "packaging_shape": "flow_wrap",
            "shelf_life_prediction_days": "5-14 days",
            "cost_estimate": "Low - approx Rs 1-3 per unit",
            "qr_traceability_note": "Link QR to bake date, batch number, and best-before date",
        }
    else:
        result = {
            "material": "Corrugated Cardboard Box with inner liner",
            "reasoning": "General-purpose sturdy packaging suitable for ambient storage and transport.",
            "otr_value": "Not a primary barrier layer",
            "wvtr_value": "Moderate (liner-dependent)",
            "film_thickness_microns": "Board: 3-5 mm equivalent",
            "sealability": "Tape-sealed or glued flaps",
            "gas_permeability": "Not a barrier packaging - relies on inner liner if needed",
            "mechanical_strength": "High stacking strength for transport",
            "map_suitability": "Not applicable",
            "map_gas_composition": "Not applicable",
            "gas_filler": "None",
            "sustainable_option": "Recycled kraft cardboard",
            "packaging_shape": "cardboard_box",
            "shelf_life_prediction_days": "Depends on inner packaging",
            "cost_estimate": "Low - approx Rs 5-10 per unit",
            "qr_traceability_note": "Link QR to origin, batch number, and handling instructions",
        }

    tier = weight_tier(_packet_grams(data) / 1000.0)
    if tier == "case":
        result["material"] += " (case pack, ~5-15 kg: outer corrugated crate" + \
            (" over a micro-perforated inner liner)" if _is_respiring(result, data) else ")")
        result["mechanical_strength"] = "High stacking/compression strength for case-load handling"
    elif tier == "bulk":
        result["material"] += " (bulk pack, 15 kg+: woven/HDPE bulk bag" + \
            (" over a micro-perforated inner liner)" if _is_respiring(result, data) else ")")
        result["mechanical_strength"] = "High tear/burst strength woven fabric for bulk handling and stacking"
        result["cost_estimate"] = "Low per kg - bulk bag cost is shared across the whole sack"

    if storage_type in ("chilled", "frozen"):
        result["reasoning"] += " Adjusted for cold storage: material also resists condensation and low-temperature brittleness."

    result["predicted_properties"] = props
    result["source"] = "offline_rule_engine"
    return result
