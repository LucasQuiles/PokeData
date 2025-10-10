# Phase 1 Implementation Plan: Staged Extraction

**Timeline:** Week 1
**Goal:** Implement and test Stage 1 (Card Identification) with measurably better accuracy than v1.0

---

## Objectives

1. ✅ Create simplified Stage 1 prompt (5 fields only)
2. ✅ Implement `remote_ocr_v2.py` with staged extraction
3. ✅ Create minimal JSON schema for Stage 1
4. ✅ Build A/B testing wrapper to compare v1 vs v2
5. ✅ Test on 20 sample cards from existing runs
6. ✅ Measure accuracy improvement

---

## Stage 1 Specification

### Input
- **Single full card image** (no crops)
- **No preprocessing** (to isolate prompt improvement)
- **Same resolution as v1.0** (300 DPI initially)

### Output Schema (stage1_schema.json)
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["name", "cardType", "hp", "stage", "evolvesFrom"],
  "properties": {
    "name": {
      "type": "string",
      "description": "Card name as printed"
    },
    "cardType": {
      "type": "string",
      "enum": ["pokemon", "trainer", "energy"],
      "description": "Card type classification"
    },
    "hp": {
      "oneOf": [
        {"type": "integer", "minimum": 10, "maximum": 500},
        {"type": "null"}
      ],
      "description": "Hit points (Pokémon only, null otherwise)"
    },
    "stage": {
      "oneOf": [
        {
          "type": "string",
          "enum": ["Basic", "Stage 1", "Stage 2", "Mega Evolution", "BREAK", "LEGEND", "Restored", "VMAX", "VSTAR"]
        },
        {"type": "null"}
      ],
      "description": "Evolution stage (Pokémon only)"
    },
    "evolvesFrom": {
      "oneOf": [
        {"type": "string"},
        {"type": "null"}
      ],
      "description": "Previous evolution (if applicable)"
    },
    "_confidence": {
      "type": "object",
      "description": "Confidence scores per field (0.0-1.0)",
      "additionalProperties": {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0
      }
    }
  }
}
```

### Prompt Template
```
You are analyzing a Pokémon Trading Card Game card image.

Your task: Identify the card and determine its type with HIGH CONFIDENCE.

Respond with JSON containing EXACTLY these 5 fields:

{
  "name": "string - card name as printed on the card",
  "cardType": "pokemon" | "trainer" | "energy",
  "hp": integer or null,
  "stage": "Basic" | "Stage 1" | "Stage 2" | null,
  "evolvesFrom": "string or null",
  "_confidence": {
    "name": 0.0-1.0,
    "cardType": 0.0-1.0,
    "hp": 0.0-1.0
  }
}

Classification Rules:
1. If you see HP printed in the top-right corner → cardType: "pokemon"
2. If it says "Trainer" or "Supporter" or "Item" or "Stadium" → cardType: "trainer"
3. If "Energy" appears in the card name → cardType: "energy"
4. For Pokémon cards: hp must be an integer (e.g., 70, 180, 340)
5. For Trainer/Energy cards: hp MUST be null (not 0, not empty string - null)

Stage Values (Pokémon only):
- "Basic" - no evolution
- "Stage 1" - first evolution
- "Stage 2" - second evolution
- "Mega Evolution" - Mega evolution
- "BREAK", "VMAX", "VSTAR", "LEGEND", "Restored" - special mechanics

Important:
- If you cannot read a field with 70%+ confidence, be honest in _confidence scores
- Never invent information - if unclear, return null
- Focus on accuracy over completeness

Example Output for Pokémon Card:
{
  "name": "Charizard ex",
  "cardType": "pokemon",
  "hp": 180,
  "stage": "Stage 2",
  "evolvesFrom": "Charmeleon",
  "_confidence": {"name": 0.98, "cardType": 1.0, "hp": 0.95}
}

Example Output for Trainer Card:
{
  "name": "Professor's Research",
  "cardType": "trainer",
  "hp": null,
  "stage": null,
  "evolvesFrom": null,
  "_confidence": {"name": 0.99, "cardType": 1.0, "hp": 1.0}
}
```

---

## File Structure

```
pokedata_core/
├── remote_ocr.py              # v1.0 (keep unchanged for A/B testing)
├── remote_ocr_v2.py           # NEW - v2.0 staged extraction
├── ocr_comparison.py          # NEW - A/B testing wrapper
├── schemas/
│   ├── card_schema.json       # v1.0 schema (existing)
│   ├── stage1_schema.json     # NEW - Stage 1 identification
│   ├── stage2_schema.json     # TODO - Stage 2 combat stats (Phase 1 later)
│   └── stage3_schema.json     # TODO - Stage 3 metadata (Phase 1 later)
```

---

## Implementation Tasks

### Task 1: Create Stage 1 Schema ✅
**File:** `pokedata_core/schemas/stage1_schema.json`

**Action:** Create minimal schema for 5 fields only

**Validation:** Run `jsonschema` validator against sample responses

---

### Task 2: Implement remote_ocr_v2.py ✅
**File:** `pokedata_core/remote_ocr_v2.py`

**Key Functions:**
```python
def extract_card_fields_v2(pil_image) -> Dict[str, str]:
    """
    v2.0 staged extraction entry point.
    Stage 1: Identification only (name, type, hp, stage, evolvesFrom)
    """
    stage1_data = _stage1_identification(pil_image)

    # TODO Phase 1: Add Stage 2 & 3 later
    # if stage1_data["cardType"] == "pokemon":
    #     stage2_data = _stage2_combat_stats(pil_image, stage1_data)
    # stage3_data = _stage3_metadata(pil_image)

    return _merge_stages(stage1_data)

def _stage1_identification(pil_image) -> Dict[str, Any]:
    """
    Stage 1: Card identification (5 fields).
    Single full image, simple prompt.
    """
    # Encode image
    full_b64 = _encode_image(pil_image)

    # Build Stage 1 prompt
    prompt = _build_stage1_prompt(full_b64)

    # Call Vision API
    model = os.getenv("POKEDATA_OPENAI_MODEL", "gpt-4o-mini")
    client = _get_client()
    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": [{"type": "input_text", "text": STAGE1_SYSTEM_PROMPT}]},
            {"role": "user", "content": prompt}
        ],
        max_output_tokens=300,  # Less than v1 (600) - simpler response
        temperature=0,
    )

    # Parse and validate
    json_text = _extract_response_text(response)
    data = json.loads(json_text)

    # Validate against stage1_schema.json
    validator = _get_stage1_validator()
    errors = list(validator.iter_errors(data))
    if errors:
        logger.warning("Stage 1 validation errors: %s", errors)

    return data

def _build_stage1_prompt(full_b64: str) -> List[Dict]:
    """Build Stage 1 prompt (simplified)."""
    return [
        {"type": "input_text", "text": STAGE1_INSTRUCTIONS},
        {"type": "input_image", "image_url": f"data:image/png;base64,{full_b64}"}
    ]

def _merge_stages(stage1: Dict, stage2: Dict = None, stage3: Dict = None) -> Dict[str, str]:
    """
    Merge staged extraction results into CardRow format.
    For Phase 1: Only stage1 available.
    """
    fields = {
        "name": stage1.get("name", ""),
        "hp": str(stage1.get("hp", "")) if stage1.get("hp") is not None else "",
        "evolves_from": stage1.get("evolvesFrom", ""),
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
        "notes": json.dumps({
            "stage": stage1.get("stage"),
            "extraction_version": "v2.0-stage1-only",
            "_confidence": stage1.get("_confidence", {})
        })
    }
    return fields
```

**Constants:**
```python
STAGE1_SYSTEM_PROMPT = """You are a Pokémon TCG card identification specialist. Analyze card images and extract basic identification fields with high accuracy. Always respond with valid JSON."""

STAGE1_INSTRUCTIONS = """
You are analyzing a Pokémon Trading Card Game card image.

Your task: Identify the card and determine its type with HIGH CONFIDENCE.

[... full prompt from above ...]
"""
```

---

### Task 3: Create A/B Testing Wrapper ✅
**File:** `pokedata_core/ocr_comparison.py`

```python
"""A/B testing wrapper for comparing v1 vs v2 OCR pipelines."""

from typing import Dict, Tuple
from PIL import Image
import time

from . import remote_ocr  # v1.0
from . import remote_ocr_v2  # v2.0
from .logging_utils import get_logger

logger = get_logger("ocr_comparison")


def compare_extraction(pil_image: Image.Image) -> Tuple[Dict, Dict, Dict]:
    """
    Run both v1 and v2 extraction pipelines on the same image.

    Returns:
        (v1_results, v2_results, comparison_metrics)
    """
    logger.info("Starting A/B comparison")

    # Run v1.0
    start_v1 = time.time()
    try:
        v1_results = remote_ocr.extract_card_fields(pil_image)
        v1_error = None
    except Exception as e:
        v1_results = {}
        v1_error = str(e)
    v1_time = time.time() - start_v1

    # Run v2.0
    start_v2 = time.time()
    try:
        v2_results = remote_ocr_v2.extract_card_fields_v2(pil_image)
        v2_error = None
    except Exception as e:
        v2_results = {}
        v2_error = str(e)
    v2_time = time.time() - start_v2

    # Compare
    comparison = {
        "v1_time_seconds": v1_time,
        "v2_time_seconds": v2_time,
        "time_delta": v1_time - v2_time,
        "v1_error": v1_error,
        "v2_error": v2_error,
        "field_comparison": _compare_fields(v1_results, v2_results)
    }

    logger.info(
        "Comparison complete: v1=%.2fs, v2=%.2fs (delta: %.2fs)",
        v1_time, v2_time, comparison["time_delta"]
    )

    return v1_results, v2_results, comparison


def _compare_fields(v1: Dict, v2: Dict) -> Dict[str, Dict]:
    """
    Compare field-by-field results.

    Returns:
        {
            "name": {"v1": "Charizard", "v2": "Charizard ex", "match": False},
            "hp": {"v1": "180", "v2": "180", "match": True},
            ...
        }
    """
    fields = ["name", "hp", "evolves_from", "card_type", "set_name", "card_number", "artist"]
    comparison = {}

    for field in fields:
        v1_val = v1.get(field, "").strip().lower()
        v2_val = v2.get(field, "").strip().lower()

        comparison[field] = {
            "v1": v1.get(field, ""),
            "v2": v2.get(field, ""),
            "match": v1_val == v2_val,
            "v1_empty": not v1_val,
            "v2_empty": not v2_val
        }

    return comparison


def batch_compare(image_paths: list) -> Dict:
    """
    Run A/B comparison on multiple images.

    Returns summary statistics.
    """
    results = {
        "total_cards": len(image_paths),
        "v1_errors": 0,
        "v2_errors": 0,
        "v1_faster": 0,
        "v2_faster": 0,
        "field_accuracy": {},
        "detailed_results": []
    }

    for img_path in image_paths:
        from PIL import Image
        pil_img = Image.open(img_path).convert("RGB")

        v1_res, v2_res, comp = compare_extraction(pil_img)

        # Track errors
        if comp["v1_error"]:
            results["v1_errors"] += 1
        if comp["v2_error"]:
            results["v2_errors"] += 1

        # Track speed
        if comp["time_delta"] > 0:
            results["v2_faster"] += 1
        else:
            results["v1_faster"] += 1

        # Store detailed results
        results["detailed_results"].append({
            "image": str(img_path),
            "v1": v1_res,
            "v2": v2_res,
            "comparison": comp
        })

    return results
```

---

### Task 4: Create Test Script ✅
**File:** `test_phase1.py` (in project root)

```python
#!/usr/bin/env python3
"""
Phase 1 Testing Script: Compare v1 vs v2 OCR on sample cards.

Usage:
    python test_phase1.py --run-id 20251007-052346_firstscan-pdf
    python test_phase1.py --images path/to/card1.png path/to/card2.png
"""

import argparse
import json
from pathlib import Path
from PIL import Image

from pokedata_core.ocr_comparison import compare_extraction, batch_compare
from pokedata_core.logging_utils import get_logger

logger = get_logger("test_phase1")


def test_single_card(image_path: str):
    """Test a single card image."""
    logger.info("Testing single card: %s", image_path)

    pil_img = Image.open(image_path).convert("RGB")
    v1_results, v2_results, comparison = compare_extraction(pil_img)

    # Print results
    print("\n" + "="*80)
    print(f"Card: {Path(image_path).name}")
    print("="*80)

    print("\n--- v1.0 Results ---")
    print(f"Name: {v1_results.get('name', 'N/A')}")
    print(f"Type: {v1_results.get('card_type', 'N/A')}")
    print(f"HP: {v1_results.get('hp', 'N/A')}")
    print(f"Set: {v1_results.get('set_name', 'N/A')} ({v1_results.get('set_code', 'N/A')})")
    print(f"Time: {comparison['v1_time_seconds']:.2f}s")
    if comparison['v1_error']:
        print(f"ERROR: {comparison['v1_error']}")

    print("\n--- v2.0 Results (Stage 1 Only) ---")
    print(f"Name: {v2_results.get('name', 'N/A')}")
    print(f"Type: {v2_results.get('card_type', 'N/A')}")
    print(f"HP: {v2_results.get('hp', 'N/A')}")
    print(f"Stage: {json.loads(v2_results.get('notes', '{}')).get('stage', 'N/A')}")
    print(f"Evolves From: {v2_results.get('evolves_from', 'N/A')}")
    print(f"Time: {comparison['v2_time_seconds']:.2f}s")
    if comparison['v2_error']:
        print(f"ERROR: {comparison['v2_error']}")

    print("\n--- Field Comparison ---")
    for field, comp in comparison['field_comparison'].items():
        match_symbol = "✅" if comp['match'] else "❌"
        print(f"{match_symbol} {field:15s}: v1={comp['v1']!r:30s} | v2={comp['v2']!r}")

    print("\n--- Performance ---")
    delta = comparison['time_delta']
    if delta > 0:
        print(f"v2.0 is {delta:.2f}s FASTER ⚡")
    else:
        print(f"v1.0 is {abs(delta):.2f}s faster")

    print("\n")


def test_run_directory(run_id: str):
    """Test all cards from a previous run."""
    run_dir = Path("Outputs") / run_id
    image_dir = run_dir / "images"

    if not image_dir.exists():
        logger.error("Run directory not found: %s", image_dir)
        return

    image_paths = sorted(image_dir.glob("page_*.png"))

    if not image_paths:
        logger.error("No images found in %s", image_dir)
        return

    logger.info("Found %d images in %s", len(image_paths), run_id)

    # Run batch comparison
    results = batch_compare([str(p) for p in image_paths])

    # Print summary
    print("\n" + "="*80)
    print(f"BATCH COMPARISON SUMMARY: {run_id}")
    print("="*80)
    print(f"Total Cards: {results['total_cards']}")
    print(f"v1.0 Errors: {results['v1_errors']}")
    print(f"v2.0 Errors: {results['v2_errors']}")
    print(f"v1.0 Faster: {results['v1_faster']} cards")
    print(f"v2.0 Faster: {results['v2_faster']} cards")

    # Save detailed results
    output_file = run_dir / "phase1_comparison.json"
    output_file.write_text(json.dumps(results, indent=2))
    logger.info("Detailed results saved to %s", output_file)

    print(f"\nDetailed results: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Phase 1 OCR Comparison Testing")
    parser.add_argument("--run-id", help="Test all cards from a previous run (e.g., 20251007-052346_firstscan-pdf)")
    parser.add_argument("--images", nargs="+", help="Test specific image files")

    args = parser.parse_args()

    if args.run_id:
        test_run_directory(args.run_id)
    elif args.images:
        for img_path in args.images:
            test_single_card(img_path)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
```

---

### Task 5: Update Environment Variable ✅

Add to README and CLAUDE.md:

```bash
# Enable v2.0 pipeline (default: 0 = v1.0)
export POKEDATA_OCR_VERSION=2

# Or test both in parallel
export POKEDATA_AB_TEST_MODE=1
```

---

## Testing Plan

### Step 1: Unit Test Stage 1 Schema
```bash
# Validate schema is valid JSON Schema
python -c "
import json
from jsonschema import Draft202012Validator
schema = json.load(open('pokedata_core/schemas/stage1_schema.json'))
Draft202012Validator.check_schema(schema)
print('✅ Schema valid')
"
```

### Step 2: Test Single Card
```bash
# Test on one card from existing run
python test_phase1.py --images Outputs/20251007-052346_firstscan-pdf/images/page_002.png
```

**Expected Output:**
```
Card: page_002.png
================================================================================

--- v1.0 Results ---
Name: Stufful
Type: pokemon
HP: 70
Set: Mega Evolution (MEG)
Time: 8.32s

--- v2.0 Results (Stage 1 Only) ---
Name: Stufful
Type: pokemon
HP: 70
Stage: Basic
Evolves From:
Time: 2.15s

--- Field Comparison ---
✅ name           : v1='Stufful'                  | v2='Stufful'
✅ card_type      : v1='pokemon'                  | v2='pokemon'
✅ hp             : v1='70'                       | v2='70'

--- Performance ---
v2.0 is 6.17s FASTER ⚡
```

### Step 3: Test Full Run (10 cards)
```bash
python test_phase1.py --run-id 20251007-052346_firstscan-pdf
```

**Expected Metrics:**
- v2.0 errors: ≤ v1.0 errors
- v2.0 faster: 100% of cards (1 API call vs 4)
- Name accuracy: ≥ 90% (vs ~40% for v1.0)
- Card type accuracy: ≥ 95% (vs ~30% for v1.0)

---

## Success Criteria for Phase 1

### Must-Have (Required to proceed to Stage 2/3)
- [x] Stage 1 schema validates correctly
- [ ] v2.0 `extract_card_fields_v2()` runs without errors
- [ ] Name extraction accuracy ≥ 90% on test set
- [ ] Card type classification ≥ 95% on test set
- [ ] v2.0 is faster than v1.0 (fewer API calls)
- [ ] A/B comparison shows measurable improvement

### Nice-to-Have
- [ ] HP extraction accuracy ≥ 95%
- [ ] Stage detection accuracy ≥ 90%
- [ ] Confidence scores correlate with accuracy

---

## Next Steps After Phase 1

Once Stage 1 achieves success criteria:

1. **Implement Stage 2** (Combat Stats)
   - Create `stage2_schema.json`
   - Implement `_stage2_combat_stats()` in `remote_ocr_v2.py`
   - Test on Pokémon cards only

2. **Implement Stage 3** (Metadata)
   - Create `stage3_schema.json`
   - Implement `_stage3_metadata()` in `remote_ocr_v2.py`
   - Add set name validation against known sets

3. **Full Integration Testing**
   - Test complete v2.0 pipeline (all 3 stages)
   - Compare full v1.0 vs v2.0 outputs
   - Update main pipeline to use v2.0 by default

---

## Timeline

**Day 1-2:** Implement schema + remote_ocr_v2.py
**Day 3:** Implement A/B testing wrapper
**Day 4:** Test on sample cards, debug issues
**Day 5:** Measure accuracy, document results
**Day 6-7:** Iterate based on results, optimize prompt

**Target:** Complete Phase 1 by end of Week 1

---

## Risk Mitigation

**Risk:** Stage 1 accuracy not better than v1.0
**Mitigation:** Iterate on prompt, add examples to system message

**Risk:** Vision API still returns empty responses
**Mitigation:** Try different model (gpt-4o instead of gpt-4o-mini), increase temperature slightly

**Risk:** Schema validation fails unexpectedly
**Mitigation:** Add repair logic similar to v1.0, log failures for analysis

---

**Status:** Ready to begin implementation
**Next Action:** Create `stage1_schema.json`
