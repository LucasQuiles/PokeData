"""Remote OCR v2.0 - Staged Extraction Pipeline.

This module implements a redesigned OCR pipeline with three focused stages:
- Stage 1: Card Identification (name, type, HP, stage, evolvesFrom)
- Stage 2: Combat Stats (abilities, attacks, weakness, resistance, retreat) [TODO]
- Stage 3: Metadata (set, card number, artist, rarity, year) [TODO]

Phase 1 (current): Stage 1 only
"""

from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

from jsonschema import Draft202012Validator
from openai import OpenAI

from .logging_utils import get_logger


logger = get_logger("remote_ocr_v2")

_CLIENT: Optional[OpenAI] = None
_STAGE1_SCHEMA = None
_STAGE1_VALIDATOR: Optional[Draft202012Validator] = None
STAGE1_SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "stage1_schema.json"


# ============================================================================
# System Prompts & Instructions
# ============================================================================

STAGE1_SYSTEM_PROMPT = """You are a Pokémon TCG card identification specialist. Your task is to analyze card images and extract basic identification fields with high accuracy. Always respond with valid JSON matching the specified schema. Be conservative: if you cannot read a field with 70%+ confidence, indicate this in your confidence scores."""

STAGE1_INSTRUCTIONS = """You are analyzing a Pokémon Trading Card Game card image.

Your task: Identify the card and determine its type with HIGH CONFIDENCE.

Respond with JSON containing EXACTLY these 5 fields:

{
  "name": "string - card name as printed on the card",
  "cardType": "pokemon" | "trainer" | "energy",
  "hp": integer or null,
  "stage": "Basic" | "Stage 1" | "Stage 2" | "Mega Evolution" | "BREAK" | "VMAX" | "VSTAR" | "V" | "GX" | "EX" | "ex" | "LEGEND" | "Restored" | null,
  "evolvesFrom": "string or null",
  "_confidence": {
    "name": 0.0-1.0,
    "cardType": 0.0-1.0,
    "hp": 0.0-1.0,
    "stage": 0.0-1.0,
    "evolvesFrom": 0.0-1.0
  }
}

Classification Rules:
1. If you see HP printed in the top-right corner → cardType: "pokemon"
2. If it says "Trainer" or "Supporter" or "Item" or "Stadium" or "Tool" → cardType: "trainer"
3. If "Energy" appears in the card name → cardType: "energy"
4. For Pokémon cards: hp must be an integer (e.g., 70, 180, 340)
5. For Trainer/Energy cards: hp MUST be null (not 0, not empty string - null)

Stage Values (Pokémon only):
- "Basic" - no evolution, or explicitly says "Basic" on card
- "Stage 1" - first evolution (card shows "Stage 1")
- "Stage 2" - second evolution (card shows "Stage 2")
- "Mega Evolution" - card shows "M" prefix (e.g., "M Charizard-EX")
- "BREAK", "VMAX", "VSTAR", "V", "GX", "EX", "ex" - special mechanics printed on card
- "LEGEND", "Restored" - rare mechanics
- null - for Trainer/Energy cards or if stage cannot be determined

evolvesFrom:
- Look for text like "Evolves from Charmeleon" below the card name
- For Basic Pokémon or Trainer/Energy cards, use null
- Be precise: extract the exact name printed

Important:
- If you cannot read a field with 70%+ confidence, set confidence score < 0.7
- Never invent information - if unclear, return null and low confidence
- Focus on accuracy over completeness
- Confidence scores should reflect your actual certainty

Example Output for Pokémon Card:
{
  "name": "Charizard ex",
  "cardType": "pokemon",
  "hp": 180,
  "stage": "Stage 2",
  "evolvesFrom": "Charmeleon",
  "_confidence": {"name": 0.98, "cardType": 1.0, "hp": 0.95, "stage": 0.92, "evolvesFrom": 0.88}
}

Example Output for Trainer Card:
{
  "name": "Professor's Research",
  "cardType": "trainer",
  "hp": null,
  "stage": null,
  "evolvesFrom": null,
  "_confidence": {"name": 0.99, "cardType": 1.0, "hp": 1.0, "stage": 1.0, "evolvesFrom": 1.0}
}

Example Output for Basic Pokémon:
{
  "name": "Pikachu",
  "cardType": "pokemon",
  "hp": 60,
  "stage": "Basic",
  "evolvesFrom": null,
  "_confidence": {"name": 0.99, "cardType": 1.0, "hp": 0.97, "stage": 0.95, "evolvesFrom": 1.0}
}
"""


# ============================================================================
# Client & Validator Initialization
# ============================================================================

def _get_client() -> OpenAI:
    """Get or create OpenAI client."""
    global _CLIENT
    if _CLIENT is None:
        api_key = os.getenv("POKEDATA_OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "POKEDATA_OPENAI_API_KEY environment variable not set; remote OCR unavailable."
            )
        _CLIENT = OpenAI(api_key=api_key)
    return _CLIENT


def _get_stage1_validator() -> Draft202012Validator:
    """Get or create Stage 1 JSON schema validator."""
    global _STAGE1_SCHEMA, _STAGE1_VALIDATOR
    if _STAGE1_VALIDATOR is None:
        if not STAGE1_SCHEMA_PATH.exists():
            raise RuntimeError(f"Stage 1 schema not found at {STAGE1_SCHEMA_PATH}")
        _STAGE1_SCHEMA = json.loads(STAGE1_SCHEMA_PATH.read_text())
        _STAGE1_VALIDATOR = Draft202012Validator(_STAGE1_SCHEMA)
    return _STAGE1_VALIDATOR


# ============================================================================
# Image Encoding
# ============================================================================

def _encode_image(pil_img) -> str:
    """Encode PIL Image to base64 PNG."""
    buffer = io.BytesIO()
    pil_img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


# ============================================================================
# Stage 1: Card Identification
# ============================================================================

def _build_stage1_prompt(full_b64: str) -> List[Dict[str, str]]:
    """
    Build Stage 1 prompt (simple, single image).

    Args:
        full_b64: Base64-encoded full card image

    Returns:
        Prompt content list for Vision API
    """
    return [
        {"type": "input_text", "text": STAGE1_INSTRUCTIONS},
        {"type": "input_image", "image_url": f"data:image/png;base64,{full_b64}"}
    ]


def _stage1_identification(pil_image) -> Dict[str, Any]:
    """
    Stage 1: Card Identification.

    Extracts 5 critical fields:
    - name (string)
    - cardType (pokemon | trainer | energy)
    - hp (integer or null)
    - stage (string or null)
    - evolvesFrom (string or null)

    Args:
        pil_image: PIL Image of the card

    Returns:
        Dict with stage1 fields + _confidence scores

    Raises:
        RuntimeError: If API key not set
        ValueError: If API returns invalid JSON
        Exception: If API call fails
    """
    logger.debug("Starting Stage 1 identification")

    # Encode full card image
    full_b64 = _encode_image(pil_image)

    # Build prompt
    prompt = _build_stage1_prompt(full_b64)

    # Get model from env (default: gpt-4o-mini)
    model = os.getenv("POKEDATA_OPENAI_MODEL", "gpt-4o-mini")

    # Call Vision API
    client = _get_client()
    logger.debug("Calling OpenAI Vision API with model=%s", model)

    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": [
                    {"type": "input_text", "text": STAGE1_SYSTEM_PROMPT}
                ]
            },
            {"role": "user", "content": prompt}
        ],
        max_output_tokens=300,  # Less than v1.0 (600) - simpler response expected
        temperature=0,
    )

    # Extract JSON from response
    json_text = _extract_response_text(response)
    json_text = json_text.strip()

    # Strip markdown code blocks if present
    if json_text.startswith("```"):
        lines = [line for line in json_text.splitlines() if not line.strip().startswith("```")]
        json_text = "\n".join(lines).strip()

    logger.debug("Stage 1 raw response: %s", json_text[:200])

    # Parse JSON
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        logger.error("Stage 1 returned invalid JSON: %s", exc)
        logger.error("Raw response: %s", json_text)
        raise ValueError(f"Stage 1 JSON parsing failed: {exc}")

    # Validate against schema
    validator = _get_stage1_validator()
    errors = list(validator.iter_errors(data))

    if errors:
        error_messages = [f"{list(err.path)}: {err.message}" for err in errors]
        logger.warning("Stage 1 schema validation errors: %s", error_messages)
        # Don't raise - allow processing to continue with warnings

    # Ensure _confidence exists
    if "_confidence" not in data:
        logger.warning("Stage 1 response missing _confidence, adding defaults")
        data["_confidence"] = {
            "name": 0.5,
            "cardType": 0.5,
            "hp": 0.5,
            "stage": 0.5,
            "evolvesFrom": 0.5
        }

    logger.info(
        "Stage 1 complete: name=%s, type=%s, hp=%s, conf(name)=%.2f",
        data.get("name", ""),
        data.get("cardType", ""),
        data.get("hp", ""),
        data.get("_confidence", {}).get("name", 0.0)
    )

    return data


# ============================================================================
# Stage 2 & 3 Stubs (TODO)
# ============================================================================

def _stage2_combat_stats(pil_image, stage1_data: Dict) -> Dict[str, Any]:
    """
    Stage 2: Combat Stats (TODO - Phase 1 future).

    Will extract:
    - types
    - abilities
    - attacks
    - weakness
    - resistance
    - retreatCost

    Args:
        pil_image: PIL Image
        stage1_data: Results from Stage 1 (for context)

    Returns:
        Dict with combat stats
    """
    logger.warning("Stage 2 not implemented yet (Phase 1)")
    return {}


def _stage3_metadata(pil_image) -> Dict[str, Any]:
    """
    Stage 3: Metadata (TODO - Phase 1 future).

    Will extract:
    - set name
    - card number
    - artist
    - rarity
    - print year

    Args:
        pil_image: PIL Image

    Returns:
        Dict with metadata
    """
    logger.warning("Stage 3 not implemented yet (Phase 1)")
    return {}


# ============================================================================
# Merge Stages & Map to CardRow Format
# ============================================================================

def _merge_stages(stage1: Dict, stage2: Dict = None, stage3: Dict = None) -> Dict[str, str]:
    """
    Merge staged extraction results into CardRow format.

    For Phase 1: Only stage1 available, other fields left empty.

    Args:
        stage1: Stage 1 identification data
        stage2: Stage 2 combat stats (optional, TODO)
        stage3: Stage 3 metadata (optional, TODO)

    Returns:
        Dict matching CardRow field names
    """
    # Convert HP to string (empty if null)
    hp_value = stage1.get("hp")
    hp_str = str(hp_value) if hp_value is not None else ""

    # Build notes JSON
    notes = {
        "extraction_version": "v2.0-stage1-only",
        "stage": stage1.get("stage"),
        "_confidence": stage1.get("_confidence", {}),
        "schema_version": "stage1"
    }

    # Map to CardRow format
    fields = {
        "name": stage1.get("name", ""),
        "hp": hp_str,
        "evolves_from": stage1.get("evolvesFrom") or "",
        "card_type": stage1.get("cardType", "unknown"),

        # Empty for now (filled in Stage 2/3 later)
        "ability_name": "",
        "ability_text": "",
        "attacks": "",
        "set_name": "",
        "set_code": "",
        "card_number": "",
        "artist": "",
        "weakness": "",
        "resistance": "",
        "retreat": "",
        "rarity": "",

        # Store metadata in notes
        "notes": json.dumps(notes, ensure_ascii=False)
    }

    return fields


# ============================================================================
# Public API
# ============================================================================

def extract_card_fields_v2(pil_image) -> Dict[str, str]:
    """
    v2.0 staged extraction entry point.

    Phase 1: Stage 1 only (identification)
    Future: Will call Stage 2 (combat stats) and Stage 3 (metadata)

    Args:
        pil_image: PIL Image of card

    Returns:
        Dict with CardRow fields (compatible with v1.0 output format)

    Raises:
        RuntimeError: If API key not set
        ValueError: If API returns invalid response
    """
    logger.info("Starting v2.0 extraction (Stage 1 only)")

    # Stage 1: Identification
    stage1_data = _stage1_identification(pil_image)

    # TODO Phase 1: Implement Stage 2 & 3
    # if stage1_data["cardType"] == "pokemon":
    #     stage2_data = _stage2_combat_stats(pil_image, stage1_data)
    # else:
    #     stage2_data = {}
    #
    # stage3_data = _stage3_metadata(pil_image)

    # For now, just Stage 1
    stage2_data = None
    stage3_data = None

    # Merge and return
    result = _merge_stages(stage1_data, stage2_data, stage3_data)

    logger.info("v2.0 extraction complete: name=%s, type=%s", result["name"], result["card_type"])

    return result


# ============================================================================
# Utility Functions
# ============================================================================

def _extract_response_text(response) -> str:
    """
    Extract text content from OpenAI Responses API response.

    Args:
        response: OpenAI API response object

    Returns:
        Extracted text content

    Raises:
        ValueError: If no text content found
    """
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

    except Exception as exc:
        logger.warning("Failed to read response text: %s", exc)

    raise ValueError("No text output returned from OpenAI response")
