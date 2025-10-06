"""Remote OCR integration backed by the OpenAI Responses API."""

from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from jsonschema import Draft202012Validator
from openai import OpenAI

from .logging_utils import get_logger


logger = get_logger("remote_ocr")

_CLIENT: Optional[OpenAI] = None
_CARD_SCHEMA = None
_VALIDATOR: Optional[Draft202012Validator] = None
SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "card_schema.json"


def _get_client() -> OpenAI:
    global _CLIENT
    if _CLIENT is None:
        api_key = os.getenv("POKEDATA_OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "POKEDATA_OPENAI_API_KEY environment variable not set; remote OCR unavailable."
            )
        _CLIENT = OpenAI(api_key=api_key)
    return _CLIENT


def _get_validator() -> Draft202012Validator:
    global _CARD_SCHEMA, _VALIDATOR
    if _VALIDATOR is None:
        if not SCHEMA_PATH.exists():
            raise RuntimeError(f"Card schema not found at {SCHEMA_PATH}")
        _CARD_SCHEMA = json.loads(SCHEMA_PATH.read_text())
        _VALIDATOR = Draft202012Validator(_CARD_SCHEMA)
    return _VALIDATOR


def _encode_image(pil_img) -> str:
    buffer = io.BytesIO()
    pil_img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _build_prompt(full_b64: str, header_b64: str, footer_b64: str) -> List[Dict[str, str]]:
    instructions = (
        "You are a strict Pokémon card transcriber. Respond with JSON matching the provided schema. "
        "Never guess; if text is unreadable set the value to null and append the field name to notes.unreadable. "
        "Convert icons to words using the 11 energy types (Colorless, Darkness, Dragon, Fairy, Fighting, Fire, Grass, Lightning, Metal, Psychic, Water). "
        "Stages are one of: Basic, Stage 1, Stage 2, Restored, Mega Evolution, BREAK, LEGEND. "
        "Return confidence scores (0..1) in the _confidence object for each field."
    )

    format_hint = (
        "Return JSON only. Example skeleton: {\n"
        "  \"name\": \"Charizard\",\n"
        "  \"stage\": \"Stage 2\",\n"
        "  \"evolvesFrom\": \"Charmeleon\",\n"
        "  \"hp\": 170,\n"
        "  \"types\": [\"Fire\"],\n"
        "  \"stamps\": [],\n"
        "  \"promo\": {\"isPromo\": false, \"series\": null, \"promoNumber\": null},\n"
        "  \"number\": \"014/189\",\n"
        "  \"set\": {\"name\": \"Darkness Ablaze\", \"code\": \"DAA\", \"total\": 189, \"symbolCode\": null},\n"
        "  \"setboxLetters\": \"MEG\",\n"
        "  \"printYear\": 2020,\n"
        "  \"illustrator\": \"5ban Graphics\",\n"
        "  \"text\": {\n"
        "    \"abilities\": [{\"name\": \"Roaring Resolve\", \"text\": \"...\", \"kind\": \"Ability\"}],\n"
        "    \"attacks\": [{\"name\": \"Flare Blitz\", \"cost\": [\"Fire\",\"Fire\"], \"damage\": \"120+\", \"text\": \"...\"}],\n"
        "    \"weaknesses\": [{\"type\": \"Water\", \"value\": \"×2\"}],\n"
        "    \"resistances\": [],\n"
        "    \"retreatCost\": [\"Colorless\", \"Colorless\"]\n"
        "  },\n"
        "  \"notes\": {\"unreadable\": []},\n"
        "  \"_confidence\": {\"name\": 0.95}\n"
        "}"
    )

    return [
        {"type": "input_text", "text": instructions},
        {"type": "input_text", "text": format_hint},
        {"type": "input_text", "text": "Primary card image:"},
        {"type": "input_image", "image_url": f"data:image/png;base64,{full_b64}"},
        {"type": "input_text", "text": "Header crop (name, stage/evolves from, HP, type banner):"},
        {"type": "input_image", "image_url": f"data:image/png;base64,{header_b64}"},
        {"type": "input_text", "text": "Footer crop (setbox letters, card number, illustrator, year):"},
        {"type": "input_image", "image_url": f"data:image/png;base64,{footer_b64}"},
    ]


def extract_card_fields(pil_image) -> Dict[str, str]:
    """Return card row data enriched by structured JSON from the OpenAI Vision API."""

    width, height = pil_image.size
    header_crop = pil_image.crop((0, 0, width, int(height * 0.25)))
    footer_crop = pil_image.crop((0, int(height * 0.75), width, height))

    full_b64 = _encode_image(pil_image)
    header_b64 = _encode_image(header_crop)
    footer_b64 = _encode_image(footer_crop)

    prompt = _build_prompt(full_b64, header_b64, footer_b64)
    model = os.getenv("POKEDATA_OPENAI_MODEL", "gpt-4o-mini")

    client = _get_client()
    validator = _get_validator()
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You are a data extraction assistant. Always respond with a single JSON object that matches the provided schema."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": prompt
                + [
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{full_b64}",
                    }
                ],
            },
        ],
        max_output_tokens=600,
        temperature=0,
    )

    json_text = _extract_response_text(response)
    json_text = json_text.strip()
    if json_text.startswith("```"):
        lines = [line for line in json_text.splitlines() if not line.strip().startswith("```")]
        json_text = "\n".join(lines).strip()
    logger.debug("Remote OCR raw response: %s", json_text)
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        dump_path = _write_debug_payload(json_text)
        logger.warning(
            "Remote OCR returned invalid JSON: %s | saved payload to %s",
            exc,
            dump_path,
        )
        raise

    data = _normalize_payload(data)

    errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
    if errors:
        formatted = "; ".join(f"{list(err.path)}: {err.message}" for err in errors)
        dump_path = _write_debug_payload(data)
        logger.warning("Schema validation failed, payload saved to %s", dump_path)
        raise ValueError(f"Remote OCR JSON failed validation: {formatted}")

    card_fields = _map_structured_to_cardrow(data)
    card_fields["_structured_raw"] = data
    return card_fields


def _map_structured_to_cardrow(data: Dict[str, object]) -> Dict[str, str]:
    fields = {
        "name": str(data.get("name", "")).strip(),
        "hp": str(data.get("hp", "")),
        "evolves_from": str(data.get("evolvesFrom", "")).strip(),
        "ability_name": "",
        "ability_text": "",
        "attacks": "",
        "set_code": "",
        "set_name": "",
        "card_number": str(data.get("number", "")).strip(),
        "artist": str(data.get("illustrator", "")).strip(),
        "weakness": "",
        "resistance": "",
        "retreat": "",
        "notes": "",
        "rarity": str(data.get("rarity", "")),
    }

    hp_val = data.get("hp")
    if isinstance(hp_val, int):
        fields["hp"] = str(hp_val)

    text_block = data.get("text", {})
    abilities = []
    attacks = []
    weaknesses = []
    resistances = []
    retreat_cost = []

    if isinstance(text_block, dict):
        # Abilities
        for ability in text_block.get("abilities", []) or []:
            name = ability.get("name", "") if isinstance(ability, dict) else ""
            text = ability.get("text", "") if isinstance(ability, dict) else ""
            if name:
                abilities.append(name)
                if not fields["ability_name"]:
                    fields["ability_name"] = name
                if not fields["ability_text"]:
                    fields["ability_text"] = text

        # Attacks
        for attack in text_block.get("attacks", []) or []:
            if not isinstance(attack, dict):
                continue
            name = attack.get("name", "")
            cost_list = [c for c in attack.get("cost", []) or [] if isinstance(c, str)]
            damage = attack.get("damage", "")
            effect = attack.get("text", "")
            cost_str = "/".join(cost_list)
            damage_str = str(damage) if damage is not None else ""
            pieces = [part for part in [name, cost_str, damage_str, effect] if part]
            attacks.append(" :: ".join(pieces))

        # Weaknesses / Resistances
        for wk in text_block.get("weaknesses", []) or []:
            if isinstance(wk, dict):
                wt = wk.get("type", "")
                val = wk.get("value", "")
                weaknesses.append(f"{wt} {val}".strip())

        for rs in text_block.get("resistances", []) or []:
            if isinstance(rs, dict):
                rt = rs.get("type", "")
                val = rs.get("value", "")
                resistances.append(f"{rt} {val}".strip())

        retreat_cost = [c for c in text_block.get("retreatCost", []) or [] if isinstance(c, str)]

    if abilities and not fields["ability_text"]:
        fields["ability_text"] = "; ".join(abilities)
    if attacks:
        fields["attacks"] = " | ".join(attacks)
    if weaknesses:
        fields["weakness"] = " | ".join(weaknesses)
    if resistances:
        fields["resistance"] = " | ".join(resistances)
    if retreat_cost:
        fields["retreat"] = " / ".join(retreat_cost)

    set_block = data.get("set", {})
    if isinstance(set_block, dict):
        fields["set_name"] = str(set_block.get("name", ""))
        code = set_block.get("code")
        if isinstance(code, str):
            fields["set_code"] = code

    setbox_letters = data.get("setboxLetters")
    promo = data.get("promo") if isinstance(data.get("promo"), dict) else {}
    stage = data.get("stage", "")
    types = data.get("types", [])
    print_year = data.get("printYear")

    notes_value = data.get("notes")
    if isinstance(notes_value, str):
        try:
            notes_value = json.loads(notes_value)
        except json.JSONDecodeError:
            notes_value = {"raw": notes_value}

    if not isinstance(notes_value, dict):
        notes_value = {}

    notes_payload = {
        "stage": stage,
        "types": types,
        "setboxLetters": setbox_letters,
        "isPromo": promo.get("isPromo") if isinstance(promo, dict) else None,
        "promoSeries": promo.get("series") if isinstance(promo, dict) else None,
        "promoNumber": promo.get("promoNumber") if isinstance(promo, dict) else None,
        "printYear": print_year,
    }
    for key, value in notes_payload.items():
        if value not in (None, "", []):
            notes_value[key] = value

    if notes_value:
        fields["notes"] = json.dumps(notes_value, ensure_ascii=False)

    return fields


def _write_debug_payload(payload) -> Path:
    debug_dir = Path("logs/remote_debug")
    debug_dir.mkdir(parents=True, exist_ok=True)
    filename = f"payload_{len(list(debug_dir.glob('payload_*.json'))):04d}.json"
    dump_path = debug_dir / filename
    try:
        if isinstance(payload, str):
            dump_path.write_text(payload, encoding="utf-8")
        else:
            dump_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as exc:  # pragma: no cover
        logger.debug("Failed to write debug payload: %s", exc)
    return dump_path


def _normalize_payload(data: Dict[str, object]) -> Dict[str, object]:
    result = dict(data)

    def _clean_str(value, default=""):
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return str(value)
        return str(value)

    for key in ["name", "stage", "evolvesFrom", "ability_name", "ability_text", "attacks", "set_code", "set_name", "card_number", "artist", "weakness", "resistance", "retreat"]:
        if key in result:
            result[key] = _clean_str(result[key])

    if isinstance(result.get("hp"), str) and result["hp"].isdigit():
        result["hp"] = int(result["hp"])
    if result.get("hp") is None:
        result["hp"] = ""

    promo = result.get("promo")
    if isinstance(promo, dict):
        for subkey in ["series", "promoNumber"]:
            if promo.get(subkey) is None:
                promo[subkey] = ""
        if promo.get("isPromo") is None:
            promo["isPromo"] = False
    elif promo is None:
        result["promo"] = {"isPromo": False, "series": "", "promoNumber": ""}

    set_block = result.get("set")
    if isinstance(set_block, dict):
        for subkey in ["name", "code", "symbolCode"]:
            if set_block.get(subkey) is None:
                set_block[subkey] = ""
        if set_block.get("total") is None:
            set_block.pop("total", None)
    elif set_block is None:
        result["set"] = {"name": "", "code": "", "symbolCode": ""}

    if result.get("setboxLetters") is None:
        result["setboxLetters"] = ""
    if result.get("illustrator") is None:
        result["illustrator"] = ""
    if result.get("printYear") is None:
        result.pop("printYear", None)

    text_block = result.get("text")
    if isinstance(text_block, dict):
        attacks = text_block.get("attacks")
        if isinstance(attacks, list):
            for attack in attacks:
                if isinstance(attack, dict):
                    if attack.get("text") is None:
                        attack["text"] = ""
                    if attack.get("damage") is None:
                        attack["damage"] = ""
        abilities = text_block.get("abilities")
        if isinstance(abilities, list):
            for ability in abilities:
                if isinstance(ability, dict) and ability.get("text") is None:
                    ability["text"] = ""
    elif text_block is None:
        result["text"] = {}

    confidence = result.get("_confidence")
    if isinstance(confidence, dict):
        for key, value in list(confidence.items()):
            if isinstance(value, (int, float)):
                continue
            if isinstance(value, dict):
                avg = None
                numeric_vals = [v for v in value.values() if isinstance(v, (int, float))]
                if numeric_vals:
                    avg = sum(numeric_vals) / len(numeric_vals)
                confidence[key] = avg if avg is not None else 0.0
            else:
                confidence[key] = 0.0
    elif confidence is not None:
        result["_confidence"] = {}

    notes_val = result.get("notes")
    if notes_val is None:
        result["notes"] = {}

    return result


def _extract_response_text(response) -> str:
    # The Responses API returns a structured object. We gather any text content.
    parts: List[str] = []
    try:
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                text_obj = getattr(content, "text", None)
                if isinstance(text_obj, str):
                    parts.append(text_obj)
                else:
                    value = getattr(text_obj, "value", None)
                    if value:
                        parts.append(value)
        if parts:
            return "\n".join(parts)
        # Fallback for .output_text helper (newer SDKs)
        text = getattr(response, "output_text", None)
        if text:
            return text
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to read response text: %s", exc)
    raise ValueError("No text output returned from OpenAI response")
