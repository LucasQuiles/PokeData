"""Remote OCR integration backed by the OpenAI Responses API."""

from __future__ import annotations

import base64
import io
import json
import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

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


def _build_prompt(
    full_b64: str, header_b64: str, middle_b64: str, footer_b64: str
) -> List[Dict[str, str]]:
    instructions = (
        "You are a meticulous Pokémon card transcriber. Always respond with a single JSON object that satisfies the schema hints below. "
        "Never invent information. If any field is unreadable, set it to null and list the JSON pointer (e.g. 'name', 'text.attacks[0].damage') in notes.unreadable. "
        "Stages must be one of: Basic, Stage 1, Stage 2, Restored, Mega Evolution, BREAK, LEGEND. "
        "Energy or type references must be converted to these canonical tokens: Colorless, Darkness, Dragon, Fairy, Fighting, Fire, Grass, Lightning, Metal, Psychic, Water."
    )

    schema_hint = (
        "Required top-level fields: name, stage, evolvesFrom, hp, types, stamps, promo, number, set, setboxLetters, printYear, illustrator, text, notes, _confidence. "
        "Within text, capture abilities (name, text, kind when printed), attacks (name, cost array, damage text or number, rules text), weaknesses/resistances (type + value such as ×2, -30), and retreatCost. "
        "Populate promo.isPromo=true only if the card is explicitly a promo; otherwise false and leave series/promoNumber null. "
        "Card number must include suffixes like TG01 or 014/189 exactly as printed. Set.name is the printed set title, and set.code is the 2-4 letter abbreviation if visible; leave null if not printed."
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
        {"type": "input_text", "text": schema_hint},
        {"type": "input_text", "text": format_hint},
        {"type": "input_text", "text": "Primary card image:"},
        {"type": "input_image", "image_url": f"data:image/png;base64,{full_b64}"},
        {"type": "input_text", "text": "Header crop (name, stage/evolves from, HP, type banner):"},
        {"type": "input_image", "image_url": f"data:image/png;base64,{header_b64}"},
        {"type": "input_text", "text": "Main text area (abilities, attacks, rules):"},
        {"type": "input_image", "image_url": f"data:image/png;base64,{middle_b64}"},
        {"type": "input_text", "text": "Footer crop (setbox letters, card number, rarity, illustrator, year):"},
        {"type": "input_image", "image_url": f"data:image/png;base64,{footer_b64}"},
    ]


def extract_card_fields(pil_image) -> Dict[str, str]:
    """Return card row data enriched by structured JSON from the OpenAI Vision API."""

    width, height = pil_image.size
    header_crop = pil_image.crop((0, 0, width, int(height * 0.25)))
    middle_crop = pil_image.crop((0, int(height * 0.25), width, int(height * 0.75)))
    footer_crop = pil_image.crop((0, int(height * 0.75), width, height))

    full_b64 = _encode_image(pil_image)
    header_b64 = _encode_image(header_crop)
    middle_b64 = _encode_image(middle_crop)
    footer_b64 = _encode_image(footer_crop)

    prompt = _build_prompt(full_b64, header_b64, middle_b64, footer_b64)
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
            {"role": "user", "content": prompt},
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
    abilities: List[str] = []
    ability_details: List[str] = []
    attacks: List[Dict[str, str]] = []
    weaknesses = []
    resistances = []
    retreat_cost = []

    if isinstance(text_block, dict):
        # Abilities
        for ability in text_block.get("abilities", []) or []:
            name = ability.get("name", "") if isinstance(ability, dict) else ""
            text = ability.get("text", "") if isinstance(ability, dict) else ""
            if name:
                ability_str = name
                if text:
                    ability_str = f"{name}: {text}"
                abilities.append(ability_str.strip())
                if not fields["ability_name"]:
                    fields["ability_name"] = name
                if text:
                    ability_details.append(text)

        # Attacks
        for attack in text_block.get("attacks", []) or []:
            if not isinstance(attack, dict):
                continue
            name = str(attack.get("name", "")) if attack.get("name") is not None else ""
            cost_list = [c for c in attack.get("cost", []) or [] if isinstance(c, str)]
            damage = attack.get("damage", "")
            effect = attack.get("text", "")
            damage_str = str(damage) if damage is not None else ""
            attacks.append(
                {
                    "name": name,
                    "cost": cost_list,
                    "damage": damage_str,
                    "text": str(effect) if effect not in (None, []) else "",
                }
            )

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

    if ability_details and not fields["ability_text"]:
        fields["ability_text"] = "\n\n".join(ability_details)
    elif abilities and not fields["ability_text"]:
        fields["ability_text"] = "; ".join(abilities)
    if attacks:
        fields["attacks"] = attacks
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
        "stamps": data.get("stamps") if isinstance(data.get("stamps"), list) else None,
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

    type_map = {
        "": "",
        "colorless": "Colorless",
        "dark": "Darkness",
        "darkness": "Darkness",
        "dragon": "Dragon",
        "fairy": "Fairy",
        "fighting": "Fighting",
        "ground": "Fighting",
        "rock": "Fighting",
        "fire": "Fire",
        "grass": "Grass",
        "leaf": "Grass",
        "lightning": "Lightning",
        "electric": "Lightning",
        "metal": "Metal",
        "steel": "Metal",
        "psychic": "Psychic",
        "ghost": "Psychic",
        "water": "Water",
        "ice": "Water",
    }

    stage_map = {
        "basic": "Basic",
        "stage 1": "Stage 1",
        "stage1": "Stage 1",
        "stage-1": "Stage 1",
        "stage 2": "Stage 2",
        "stage2": "Stage 2",
        "stage-2": "Stage 2",
        "mega evolution": "Mega Evolution",
        "mega": "Mega Evolution",
        "break": "BREAK",
        "legend": "LEGEND",
        "restored": "Restored",
    }

    stamp_aliases = {
        "pre-release": "pre-release",
        "pre release": "pre-release",
        "prerelease": "pre-release",
        "staff": "staff",
        "league": "league",
        "winner": "winner",
        "pokemon-center": "pokemon-center",
        "pokemon center": "pokemon-center",
        "pokemoncenter": "pokemon-center",
        "worlds": "worlds",
        "world championships": "worlds",
        "none": "none",
    }

    def _canonical_stamp(value: str) -> Optional[str]:
        key = value.strip().lower()
        key = key.replace("_", "-")
        key = re.sub(r"\s+", "-", key)
        return stamp_aliases.get(key)

    def _canonical_type(value: str) -> str:
        key = value.strip().lower()
        return type_map.get(key, value.strip().title())

    def _canonicalize_types(values: Iterable[str]) -> List[str]:
        cleaned: List[str] = []
        for value in values:
            if not isinstance(value, str):
                continue
            canonical = _canonical_type(value)
            if canonical and canonical not in cleaned:
                cleaned.append(canonical)
        return cleaned

    def _clean_str(value, default=""):
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return str(value)
        return str(value)

    for key in [
        "name",
        "stage",
        "evolvesFrom",
        "ability_name",
        "ability_text",
        "attacks",
        "set_code",
        "set_name",
        "card_number",
        "artist",
        "weakness",
        "resistance",
        "retreat",
    ]:
        if key in result:
            result[key] = _clean_str(result[key])

    stage_value = result.get("stage")
    if isinstance(stage_value, str):
        stage_key = stage_value.strip().lower()
        if stage_key in stage_map:
            result["stage"] = stage_map[stage_key]

    if isinstance(result.get("hp"), str) and result["hp"].isdigit():
        result["hp"] = int(result["hp"])
    if result.get("hp") is None:
        result["hp"] = ""

    stamps_value = result.get("stamps")
    if isinstance(stamps_value, list):
        cleaned_stamps: List[str] = []
        for stamp in stamps_value:
            if not isinstance(stamp, str):
                continue
            canonical_stamp = _canonical_stamp(stamp)
            if canonical_stamp and canonical_stamp not in cleaned_stamps:
                cleaned_stamps.append(canonical_stamp)
        result["stamps"] = cleaned_stamps
    else:
        result["stamps"] = []

    promo = result.get("promo")
    if isinstance(promo, dict):
        for subkey in ["series", "promoNumber"]:
            value = promo.get(subkey)
            if value is None:
                promo[subkey] = ""
            else:
                promo[subkey] = _clean_str(value).strip()
        is_promo = promo.get("isPromo")
        if isinstance(is_promo, str):
            promo["isPromo"] = is_promo.strip().lower() in {"true", "1", "yes", "y"}
        elif isinstance(is_promo, (int, float)):
            promo["isPromo"] = bool(is_promo)
        elif is_promo is None:
            promo["isPromo"] = False
    elif promo is None:
        result["promo"] = {"isPromo": False, "series": "", "promoNumber": ""}

    set_block = result.get("set")
    if isinstance(set_block, dict):
        for subkey in ["name", "code", "symbolCode"]:
            value = set_block.get(subkey)
            if value is None:
                set_block[subkey] = ""
            else:
                cleaned = _clean_str(value).strip()
                if subkey == "code":
                    cleaned = cleaned.upper()
                if subkey == "symbolCode":
                    cleaned = cleaned.upper()
                set_block[subkey] = cleaned
        total = set_block.get("total")
        if isinstance(total, str) and total.isdigit():
            set_block["total"] = int(total)
        elif isinstance(total, (int, float)):
            set_block["total"] = int(total)
        else:
            set_block.pop("total", None)
    elif set_block is None:
        result["set"] = {"name": "", "code": "", "symbolCode": ""}

    setbox_letters = result.get("setboxLetters")
    if isinstance(setbox_letters, str):
        result["setboxLetters"] = setbox_letters.strip().upper()
    else:
        result["setboxLetters"] = ""

    illustrator = result.get("illustrator")
    if illustrator is None:
        result["illustrator"] = ""
    else:
        result["illustrator"] = _clean_str(illustrator).strip()

    print_year = result.get("printYear")
    if isinstance(print_year, str):
        digits = "".join(ch for ch in print_year if ch.isdigit())
        if digits:
            year_val = int(digits)
            if 1990 <= year_val <= 2100:
                result["printYear"] = year_val
            else:
                result.pop("printYear", None)
        else:
            result.pop("printYear", None)
    elif isinstance(print_year, (int, float)):
        year_val = int(print_year)
        if 1990 <= year_val <= 2100:
            result["printYear"] = year_val
        else:
            result.pop("printYear", None)
    else:
        result.pop("printYear", None)

    text_block = result.get("text")
    if isinstance(text_block, dict):
        result_types = result.get("types")
        if isinstance(result_types, list):
            result["types"] = _canonicalize_types(result_types)

        attacks = text_block.get("attacks")
        if isinstance(attacks, list):
            for attack in attacks:
                if isinstance(attack, dict):
                    if attack.get("text") is None:
                        attack["text"] = ""
                    if attack.get("damage") is None:
                        attack["damage"] = ""
                    cost = attack.get("cost")
                    if isinstance(cost, list):
                        attack["cost"] = _canonicalize_types(cost)
        abilities = text_block.get("abilities")
        if isinstance(abilities, list):
            for ability in abilities:
                if isinstance(ability, dict) and ability.get("text") is None:
                    ability["text"] = ""
        for key in ("weaknesses", "resistances"):
            entries = text_block.get(key)
            if isinstance(entries, list):
                for entry in entries:
                    if isinstance(entry, dict):
                        poke_type = entry.get("type")
                        if isinstance(poke_type, str):
                            entry["type"] = _canonical_type(poke_type)
        retreat_cost = text_block.get("retreatCost")
        if isinstance(retreat_cost, list):
            text_block["retreatCost"] = _canonicalize_types(retreat_cost)
    elif text_block is None:
        result["text"] = {}

    def _clamp_conf(value) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0.0
        if numeric < 0.0:
            return 0.0
        if numeric > 1.0:
            return 1.0
        return float(numeric)

    confidence = result.get("_confidence")
    if isinstance(confidence, dict):
        cleaned_conf: Dict[str, float] = {}
        for key, value in confidence.items():
            if isinstance(value, dict):
                numeric_vals: List[float] = []
                for entry in value.values():
                    try:
                        numeric_vals.append(float(entry))
                    except (TypeError, ValueError):
                        continue
                if numeric_vals:
                    cleaned_conf[str(key)] = _clamp_conf(
                        sum(numeric_vals) / len(numeric_vals)
                    )
                else:
                    cleaned_conf[str(key)] = 0.0
            else:
                cleaned_conf[str(key)] = _clamp_conf(value)
        result["_confidence"] = cleaned_conf
    elif confidence is not None:
        result["_confidence"] = {}

    notes_val = result.get("notes")
    if notes_val is None:
        notes_val = {}
    elif isinstance(notes_val, list):
        notes_val = {"raw": notes_val}
    elif isinstance(notes_val, str):
        try:
            notes_val = json.loads(notes_val)
        except json.JSONDecodeError:
            notes_val = {"raw": notes_val}

    if isinstance(notes_val, dict):
        notes_val.setdefault("unreadable", [])
        if isinstance(notes_val["unreadable"], list):
            seen: set = set()
            cleaned_unreadable: List[str] = []
            for item in notes_val["unreadable"]:
                token = str(item).strip()
                if token and token not in seen:
                    cleaned_unreadable.append(token)
                    seen.add(token)
            notes_val["unreadable"] = cleaned_unreadable
        else:
            notes_val["unreadable"] = []
        result["notes"] = notes_val
    else:
        result["notes"] = {"raw": notes_val}

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
