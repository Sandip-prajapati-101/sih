"""
JSON schema the AI must follow. The AI only describes the packaging in words
(material, specs, reasoning) and predicts the missing physical properties.

It does NOT choose the 3D file or the final packaging_shape for bulk/case packs -
that structure (1 vs 2 layers, box vs bulk bag) is decided deterministically in
offline_engine.resolve_layers() from the packet weight, the same way for every
AI provider and for the offline engine, so the 3D preview is always consistent.
"""

import copy

RECOMMENDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "material": {"type": "string", "description": "Primary packaging material (e.g. LDPE, HDPE, PET, Metalized BOPP, Aluminum foil laminate, Biodegradable film, Breathable film, woven/HDPE bulk bag)"},
        "reasoning": {"type": "string", "description": "Short scientific justification referencing the predicted properties and user inputs"},
        "otr_value": {"type": "string", "description": "Oxygen Transmission Rate with unit, e.g. '5-10 cc/m2/day'"},
        "wvtr_value": {"type": "string", "description": "Water Vapor Transmission Rate with unit, e.g. '2-5 g/m2/day'"},
        "film_thickness_microns": {"type": "string", "description": "Recommended film thickness range in microns, e.g. '40-60 microns'"},
        "sealability": {"type": "string", "description": "Sealing method and approximate seal strength, e.g. 'Heat-sealable, seal strength ~25 N/15mm'"},
        "gas_permeability": {"type": "string", "description": "Qualitative gas permeability description relevant to the product"},
        "mechanical_strength": {"type": "string", "description": "Tensile strength / puncture resistance description suited to handling and transport"},
        "map_suitability": {"type": "string", "description": "Whether Modified Atmosphere Packaging is recommended and why"},
        "map_gas_composition": {"type": "string", "description": "Recommended gas mix if MAP applies, e.g. '5% O2, 15% CO2, 80% N2', else 'Not applicable'"},
        "gas_filler": {"type": "string", "description": "What to fill inside the pack (Nitrogen gas, foam net, vacuum, none)"},
        "sustainable_option": {"type": "string", "description": "Biodegradable/eco-friendly alternative material (e.g. PLA, PHA, PBAT)"},
        "packaging_shape": {"type": "string", "description": "Your best description of the primary pack shape: one of stand_up_pouch, cardboard_box, bottle, jar, flow_wrap, bulk_bag (informational only - the app re-derives the exact shape and number of layers itself from the packet weight)"},
        "shelf_life_prediction_days": {"type": "string", "description": "Estimated shelf life achievable with this packaging, in days"},
        "cost_estimate": {"type": "string", "description": "Relative packaging cost level with brief note, e.g. 'Low - approx Rs 1-2 per unit'"},
        "qr_traceability_note": {"type": "string", "description": "One-line suggestion on what a QR code on this pack should link to (batch, harvest date, storage log, expiry)"},
    },
    "required": [
        "material", "reasoning", "otr_value", "wvtr_value", "film_thickness_microns",
        "sealability", "gas_permeability", "mechanical_strength", "map_suitability",
        "map_gas_composition", "gas_filler", "sustainable_option", "packaging_shape",
        "shelf_life_prediction_days", "cost_estimate", "qr_traceability_note",
    ],
}


PACK_SHAPES = ["stand_up_pouch", "flow_wrap", "bottle", "jar", "cardboard_box", "bulk_bag"]


def build_schema(available_shapes=None):
    s = copy.deepcopy(RECOMMENDATION_SCHEMA)
    s["properties"]["packaging_layers"] = {
        "type": "array",
        "description": (
            "The real packaging structure, ORDERED from the layer touching the food "
            "to the outermost container. 1 item for a normal single-layer pack. "
            "2 items ONLY when a separate inner liner is genuinely needed inside an "
            "outer box/bag (e.g. a micro-perforated liner for fresh/respiring produce "
            "packed in a case or bulk bag) - do not add a second layer otherwise."
        ),
        "items": {"type": "string", "enum": PACK_SHAPES},
        "minItems": 1,
        "maxItems": 2,
    }
    s["properties"]["predicted_properties"] = {
        "type": "object",
        "description": "Typical literature values for this commodity, estimated from its name and category",
        "properties": {
            "moisture_pct": {"type": "number", "description": "Moisture content in %"},
            "fat_pct": {"type": "number", "description": "Oil/fat content in %"},
            "ph": {"type": "number", "description": "Typical pH"},
            "respiration_rate": {"type": "number", "description": "ml CO2/kg/hr, 0 if not living fresh produce"},
            "storage_temp_c": {"type": "number", "description": "Ideal storage temperature in degrees C, consistent with the storage type"},
            "relative_humidity_pct": {"type": "number", "description": "Ideal relative humidity in %"},
        },
        "required": ["moisture_pct", "fat_pct", "ph", "respiration_rate",
                     "storage_temp_c", "relative_humidity_pct"],
    }
    s["required"] = s["required"] + ["predicted_properties", "packaging_layers"]
    return s
