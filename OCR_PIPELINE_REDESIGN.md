# PokeData OCR Pipeline Redesign Proposal

**Date:** 2025-10-09
**Version:** 2.0 Proposal
**Status:** Design Phase

---

## Executive Summary

The current OCR pipeline has significant accuracy issues:
- **Card misclassification:** Pokémon cards incorrectly labeled as Trainers
- **Vision API failure:** Returns mostly empty/null fields with 0.0 confidence
- **Set name hallucinations:** Inventing incorrect set names
- **Poor fallback performance:** Tesseract producing gibberish

**Root Causes:**
1. Vision API overwhelmed by complex schema (20+ fields requested at once)
2. Multi-crop strategy confusing the model (4 separate image submissions)
3. Insufficient image preprocessing and resolution
4. Classification logic running AFTER extraction instead of guiding it

**Recommended Approach:** **Staged, Iterative Extraction** with simplified prompts

---

## Current Pipeline Issues (Detailed)

### Issue 1: Card Type Misclassification

**Evidence from `cards.csv`:**
```csv
card_type,name,hp,evolves_from,stage
trainer,Lunatone,,,Basic         # ❌ Lunatone is a Pokémon
trainer,Centiskorch,,Sizzlipede,Stage 1  # ❌ Centiskorch is a Pokémon
trainer,Shedinja,,Nincada,Stage 1       # ❌ Shedinja is a Pokémon
trainer,Cinderace,,Raboot,Stage 2       # ❌ Cinderace is a Pokémon
```

**Why This Happens:**
- Classification runs AFTER field extraction
- Logic checks for HP presence, but Vision API often returns `hp: ""` (empty string)
- Fallback to checking "Trainer" keywords in text, which triggers false positives

### Issue 2: Vision API Returning Empty Responses

**Evidence from `payload_0066.json`:**
```json
{
  "name": "",
  "hp": "",
  "types": [],
  "number": null,  # ❌ Schema validation error - should be string
  "notes": {
    "unreadable": [
      "name", "stage", "hp", "types", "number",
      "set.name", "set.code", "setboxLetters",
      "printYear", "illustrator", "text.abilities",
      "text.attacks", "text.weaknesses", "text.resistances"
    ]
  },
  "_confidence": {"name": 0.0}
}
```

**Why This Happens:**
- Schema is TOO COMPLEX (20+ required fields with nested structures)
- Vision API gives up and marks everything as "unreadable"
- Multi-crop approach sends 4 images with conflicting instructions

### Issue 3: Set Name Hallucinations

**Evidence from `cards.csv`:**
```csv
set_name,set_code,card_number
"Mega Evolution",MEG,111/132      # ❌ Not a set name
"Meteorite Pokémon",,033/XY       # ❌ This is a Pokédex category
"Thunder",,024/189                # ❌ This is a type
"Inca]",MEG,030/132               # ❌ Corrupted text
"Sereno",MEG,028/132              # ❌ Made-up name
```

**Why This Happens:**
- Model extracts random text fragments from card and assigns to "set_name"
- No validation against known set list
- Footer crop includes multiple text elements (set name, rarity, artist) causing confusion

### Issue 4: Poor Tesseract Fallback

**Evidence from `fallbackSuggestions`:**
```json
{
  "name": "eA",                        # ❌ Gibberish
  "artist": "OCS eyes",                # ❌ Should be "Ken Sugimori" or similar
  "set_code": "OCS",                   # ❌ Corrupted
  "name": "se cae f ee L",             # ❌ Complete nonsense
  "artist": "OGD cae cieare body nnd"  # ❌ Random characters
}
```

**Why This Happens:**
- Images not properly preprocessed for Tesseract (needs high contrast B&W)
- No region-specific optimization (name region needs different settings than ability text)
- Regex patterns too generic, matching garbage text

---

## Proposed Solution: Staged Extraction Pipeline

### Philosophy: **Simple Prompts, Multiple Passes**

Instead of asking Vision API for everything at once, break into **3 focused stages**:

1. **Stage 1: Card Identification** (Single full image, 5 fields only)
2. **Stage 2: Combat Stats** (Targeted crops, type-specific fields)
3. **Stage 3: Metadata** (Footer crop only, set/artist/number)

---

## Stage 1: Card Identification (Critical Fields Only)

**Goal:** Determine card type and extract name/HP/stage with HIGH confidence

### Prompt Design

```
You are analyzing a Pokémon TCG card. Respond with JSON containing ONLY these 5 fields:

{
  "name": "string (card name)",
  "cardType": "pokemon" | "trainer" | "energy",
  "hp": integer or null (only if Pokémon),
  "stage": "Basic" | "Stage 1" | "Stage 2" | null,
  "evolvesFrom": "string or null"
}

Rules:
- If the card shows HP in the top-right corner → cardType: "pokemon"
- If it has no HP and says "Trainer" or "Supporter" or "Item" → cardType: "trainer"
- If it says "Energy" in the name → cardType: "energy"
- Set hp to null if not a Pokémon card
- Be confident: if you can read the name with 90%+ certainty, include it
```

### Image Submission Strategy

**Single full card image only** (no crops at this stage)

**Benefits:**
- Simple schema = higher accuracy
- Model can see full context for card type determination
- Faster processing (1 API call vs 4)
- Higher confidence scores

**Expected Output:**
```json
{
  "name": "Charizard",
  "cardType": "pokemon",
  "hp": 180,
  "stage": "Stage 2",
  "evolvesFrom": "Charmeleon"
}
```

---

## Stage 2: Combat Stats (Type-Specific Extraction)

**Goal:** Extract abilities, attacks, weaknesses, retreat cost based on card type

### Prompt Design (Pokémon Cards Only)

```
You are extracting combat stats from a Pokémon TCG card.
The card name is "{name}" with {hp} HP.

Respond with JSON:

{
  "types": ["Fire", "Water", etc.],
  "abilities": [
    {"name": "...", "text": "..."}
  ],
  "attacks": [
    {"name": "...", "cost": ["Fire", "Colorless"], "damage": "120", "text": "..."}
  ],
  "weakness": {"type": "Water", "value": "×2"} or null,
  "resistance": {"type": "Fighting", "value": "-30"} or null,
  "retreatCost": ["Colorless", "Colorless"]
}

Energy types: Colorless, Darkness, Dragon, Fairy, Fighting, Fire, Grass, Lightning, Metal, Psychic, Water
```

### Image Submission Strategy

**Two targeted crops:**
1. **Middle section** (abilities & attacks text) at 600 DPI
2. **Bottom stats bar** (weakness, resistance, retreat icons)

**Benefits:**
- Higher resolution on critical areas
- Model focuses on specific regions without distraction
- Easier to validate (weakness MUST be a valid type)

---

## Stage 3: Metadata Extraction (Set Info & Artist)

**Goal:** Extract set name, card number, artist, rarity, print year

### Prompt Design

```
You are reading the footer of a Pokémon TCG card.

Respond with JSON:

{
  "setName": "Darkness Ablaze" (full set name printed on card),
  "cardNumber": "014/189" (number/total format),
  "artist": "5ban Graphics" (illustrator name after ©),
  "rarity": "Rare Holo" or null,
  "printYear": 2020 (© year)
}

Important:
- setName is the FULL set name in the bottom-left set box (e.g., "Sword & Shield")
- Do NOT confuse Pokédex category (e.g., "Fire Pokémon") with set name
- If any field is unclear, return null (do not guess)
```

### Image Submission Strategy

**Single footer crop only** (bottom 20% of card at 600 DPI)

**Benefits:**
- Isolated region reduces confusion
- Higher DPI captures small text (©2020, artist name)
- Clear instructions prevent hallucinations

**Validation Rules:**
- If `setName` is not in known set list, flag for review (don't auto-accept)
- `cardNumber` must match pattern `\d{1,3}/\d{1,3}` or `[A-Z]{2,4}\d{1,3}`
- `printYear` must be 1996-2025

---

## Improved Image Preprocessing Pipeline

### Current Issues
- Images at 300 DPI might be too low for small text
- No contrast enhancement specifically for Vision API
- Crops are fixed percentages (may cut off important text)

### Proposed Improvements

#### 1. **Adaptive DPI Scaling**
```python
def determine_optimal_dpi(file_size_mb: float) -> int:
    """
    Balance quality vs API cost.

    Small files (scans of single cards): 600 DPI
    Large files (binder pages): 400 DPI
    """
    if file_size_mb < 5:
        return 600
    elif file_size_mb < 20:
        return 400
    else:
        return 300
```

#### 2. **Smart Card Detection & Cropping**
Instead of fixed percentage crops, detect actual card boundaries:

```python
def detect_card_boundaries(image):
    """
    Use OpenCV edge detection to find card edges.
    Handles rotated/skewed cards and multiple cards per page.
    """
    # Convert to grayscale
    # Apply Canny edge detection
    # Find contours
    # Filter for rectangular shapes matching card aspect ratio (2.5:3.5)
    # Return bounding boxes
```

**Benefits:**
- Works with binder pages (9 cards per page)
- Handles slight rotation/skew automatically
- Crops tight to card edges (no background noise)

#### 3. **Contrast Enhancement for Text Regions**
```python
def enhance_for_ocr(card_image, region: str):
    """
    Apply region-specific preprocessing.

    - Footer region: High contrast, sharpen edges (for small artist text)
    - Ability text: Denoise, adaptive threshold (for paragraph text)
    - Stats bar: Color isolation (extract weakness/resistance icons)
    """
    if region == "footer":
        return sharpen_and_binarize(card_image)
    elif region == "ability_text":
        return denoise_and_adaptive_threshold(card_image)
    elif region == "stats_bar":
        return isolate_icon_regions(card_image)
```

---

## Fallback Strategy Redesign

### Current Issues
- Tesseract runs on full image with no preprocessing
- Generic regex patterns match garbage text
- No confidence scoring for fallback results

### Proposed Multi-Tier Fallback

#### Tier 1: EasyOCR (Better than Tesseract for stylized fonts)
```python
def easyocr_fallback(card_image):
    """
    EasyOCR is better at reading stylized fonts (Pokémon card names often use custom typography).
    """
    reader = easyocr.Reader(['en'])
    results = reader.readtext(card_image, detail=1)

    # Filter results by confidence
    high_confidence = [r for r in results if r[2] > 0.8]
    return extract_fields_from_ocr_results(high_confidence)
```

#### Tier 2: Layout-Based Extraction (Known Positions)
```python
KNOWN_LAYOUTS = {
    "modern_pokemon": {
        "name": {"x": 0.05, "y": 0.04, "w": 0.5, "h": 0.06},
        "hp": {"x": 0.85, "y": 0.04, "w": 0.12, "h": 0.05},
        "card_number": {"x": 0.05, "y": 0.94, "w": 0.15, "h": 0.03}
    }
}

def layout_based_extraction(card_image, layout_type="modern_pokemon"):
    """
    Crop exact regions based on known layout, then run Tesseract.
    Much higher accuracy than full-image OCR.
    """
    layout = KNOWN_LAYOUTS[layout_type]
    fields = {}

    for field_name, bbox in layout.items():
        crop = crop_region(card_image, bbox)
        enhanced = preprocess_for_tesseract(crop, field_type=field_name)
        text = pytesseract.image_to_string(enhanced, config='--psm 7')  # Single line mode
        fields[field_name] = clean_ocr_text(text, field_name)

    return fields
```

#### Tier 3: Database Lookup (If we have partial info)
```python
def fuzzy_match_card(partial_name: str, set_code: str = None):
    """
    If we have a partial name like "Chariz" and set code "DAA",
    query Pokémon TCG API for best match.
    """
    from pokemontcgsdk import Card

    query = f'name:"{partial_name}*"'
    if set_code:
        query += f' set.ptcgoCode:{set_code}'

    cards = Card.where(q=query)
    return cards[0] if cards else None
```

---

## Confidence Scoring & Human Review Triggers

### Current Issues
- Confidence scores from Vision API often 0.0
- No aggregated quality score per card
- Review dashboard threshold is static (0.9)

### Proposed Quality Scoring System

```python
class CardExtractionQuality:
    def __init__(self, card_data):
        self.card_data = card_data
        self.scores = {}

    def calculate_overall_quality(self) -> float:
        """
        Weighted quality score: 0.0 (terrible) to 1.0 (perfect)
        """
        weights = {
            "name": 0.25,        # Name is critical
            "card_number": 0.20,  # Card number is critical (for uniqueness)
            "hp": 0.10,          # HP less critical (some cards don't have it)
            "attacks": 0.15,     # Attacks important for Pokémon
            "set_name": 0.15,    # Set important for cataloging
            "artist": 0.05,      # Artist nice-to-have
            "metadata": 0.10     # Year, rarity, etc.
        }

        self.scores["name"] = self._score_name_quality()
        self.scores["card_number"] = self._score_card_number_quality()
        self.scores["hp"] = self._score_hp_quality()
        # ... etc

        overall = sum(self.scores[field] * weights[field] for field in weights)
        return overall

    def _score_name_quality(self) -> float:
        """
        1.0: Name present with high confidence (>0.9)
        0.5: Name present but low confidence OR matched via fuzzy lookup
        0.0: No name extracted
        """
        name = self.card_data.get("name", "")
        conf = self.card_data.get("_confidence", {}).get("name", 0.0)

        if not name:
            return 0.0
        if conf > 0.9:
            return 1.0
        if conf > 0.7:
            return 0.7
        return 0.5  # Fallback extraction

    def _score_card_number_quality(self) -> float:
        """
        1.0: Valid format (123/189 or TG12/TG30)
        0.5: Partial number extracted
        0.0: No number
        """
        number = self.card_data.get("card_number", "")
        if not number:
            return 0.0

        # Standard format: 001/197
        if re.fullmatch(r'\d{1,3}/\d{1,3}', number):
            return 1.0

        # Trainer Gallery: TG01/TG30
        if re.fullmatch(r'TG\d{1,2}/TG\d{1,2}', number, re.IGNORECASE):
            return 1.0

        # Promo format: SWSH123, XY-P
        if re.fullmatch(r'[A-Z]{2,4}[\-P]?\d{1,3}', number, re.IGNORECASE):
            return 1.0

        # Partial match
        return 0.5
```

### Review Triggers

```python
def needs_human_review(card_data) -> tuple[bool, list[str]]:
    """
    Return (should_review, reasons).
    """
    quality = CardExtractionQuality(card_data)
    overall = quality.calculate_overall_quality()
    reasons = []

    if overall < 0.6:
        reasons.append(f"Low overall quality ({overall:.2f})")

    if not card_data.get("name"):
        reasons.append("Missing card name (critical field)")

    if not card_data.get("card_number"):
        reasons.append("Missing card number (prevents uniqueness)")

    set_name = card_data.get("set_name", "")
    if set_name and set_name not in KNOWN_SETS:
        reasons.append(f"Unknown set name: '{set_name}' (possible hallucination)")

    if card_data.get("card_type") == "unknown":
        reasons.append("Could not determine card type")

    return (len(reasons) > 0, reasons)
```

---

## Implementation Plan

### Phase 1: Staged Extraction (Week 1)
- [ ] Implement Stage 1 prompt (identification only)
- [ ] Test on sample cards, compare accuracy vs current pipeline
- [ ] Implement Stage 2 prompt (combat stats)
- [ ] Implement Stage 3 prompt (metadata)

### Phase 2: Image Preprocessing (Week 2)
- [ ] Implement adaptive DPI selection
- [ ] Add OpenCV card boundary detection
- [ ] Add region-specific contrast enhancement
- [ ] Test with binder pages (9 cards per scan)

### Phase 3: Improved Fallback (Week 3)
- [ ] Integrate EasyOCR as Tier 1 fallback
- [ ] Implement layout-based extraction (Tier 2)
- [ ] Add fuzzy matching via Pokémon TCG API (Tier 3)
- [ ] Test fallback tiers when Vision API disabled

### Phase 4: Quality Scoring (Week 4)
- [ ] Implement CardExtractionQuality class
- [ ] Add review trigger logic
- [ ] Update review dashboard with quality scores
- [ ] Add validation against known set list

### Phase 5: Testing & Validation (Week 5)
- [ ] Process 100 sample cards from different eras (1999-2024)
- [ ] Measure accuracy: name (target: 95%), card_number (target: 90%), set (target: 85%)
- [ ] Compare v1.0 vs v2.0 pipeline side-by-side
- [ ] Document remaining edge cases

---

## Expected Improvements

### Accuracy Targets (v2.0 vs v1.0)

| Field | v1.0 Accuracy | v2.0 Target | Measurement Method |
|-------|---------------|-------------|-------------------|
| **Card Name** | ~40% | **95%+** | Manual validation of 100 cards |
| **Card Type** | ~30% | **98%+** | Pokémon vs Trainer vs Energy classification |
| **HP** | ~60% | **95%+** | Exact match for Pokémon cards |
| **Card Number** | ~50% | **90%+** | Valid format + correct number |
| **Set Name** | ~20% | **85%+** | Match against known set list |
| **Artist** | ~45% | **80%+** | Exact match (harder due to small text) |
| **Attacks** | ~35% | **85%+** | Name + cost + damage extracted |

### Processing Speed
- **v1.0:** 4 Vision API calls per card (full + 3 crops) = ~8-12 seconds
- **v2.0:** 3 Vision API calls per card (staged) = ~6-9 seconds
- **Improvement:** ~25% faster

### Cost Reduction
- **v1.0:** 4 images * $0.00075/image = $0.003 per card
- **v2.0:** 3 images * $0.00075/image = $0.00225 per card
- **Improvement:** ~25% cheaper

---

## Testing Strategy

### Test Set Creation
1. **Modern Cards (2020-2024):** 30 cards
   - Standard Pokémon, Trainer, Energy mix
   - Include ex, V, VMAX variants

2. **Mid-Era Cards (2010-2019):** 30 cards
   - EX, GX, BREAK mechanics
   - Different layout styles

3. **Vintage Cards (1999-2009):** 20 cards
   - Original Base Set through Diamond & Pearl
   - Different fonts and layouts

4. **Edge Cases:** 20 cards
   - Foil/holographic (reflections)
   - Damaged cards (creases, wear)
   - Non-English cards (test robustness)
   - Promo cards with unusual layouts

### Validation Metrics

```python
def validate_extraction_accuracy(ground_truth_csv, extracted_csv):
    """
    Compare extracted data against manually verified ground truth.
    """
    metrics = {
        "name": {"correct": 0, "total": 0, "accuracy": 0.0},
        "card_number": {"correct": 0, "total": 0, "accuracy": 0.0},
        # ... etc for each field
    }

    for gt_row, ext_row in zip(ground_truth, extracted):
        for field in metrics.keys():
            metrics[field]["total"] += 1
            if gt_row[field].lower().strip() == ext_row[field].lower().strip():
                metrics[field]["correct"] += 1

    for field in metrics:
        total = metrics[field]["total"]
        correct = metrics[field]["correct"]
        metrics[field]["accuracy"] = correct / total if total > 0 else 0.0

    return metrics
```

---

## Migration Path (v1.0 → v2.0)

### Option 1: Hard Cutover
- Deploy v2.0 as replacement
- Re-process all existing Outputs with new pipeline
- Flag differences for review

### Option 2: A/B Testing
- Run both pipelines in parallel
- Compare outputs side-by-side in review dashboard
- Gradually increase v2.0 traffic (10% → 50% → 100%)

### Option 3: Hybrid Mode
- Use v2.0 for new processing
- Keep v1.0 available as fallback option
- Allow users to choose pipeline version

**Recommendation:** **Option 2 (A/B Testing)** for 2-4 weeks before full cutover

---

## Success Criteria

### Must-Have (Required for v2.0 Release)
- [ ] Name accuracy ≥ 95%
- [ ] Card type classification ≥ 98%
- [ ] Card number accuracy ≥ 90%
- [ ] No set name hallucinations (validation against known sets)
- [ ] Quality scoring system operational
- [ ] Fallback tiers implemented and tested

### Nice-to-Have (Post-Release)
- [ ] Set name accuracy ≥ 85%
- [ ] Artist accuracy ≥ 80%
- [ ] Attack extraction ≥ 85%
- [ ] Support for non-English cards
- [ ] Support for jumbo/oversized cards

---

## Risk Mitigation

### Risk 1: Vision API Changes/Deprecation
**Mitigation:** Abstract API interface so we can swap providers (Anthropic Claude Vision, Google Vision AI, Azure Computer Vision)

### Risk 2: Cost Increase
**Mitigation:** Implement aggressive caching (SHA1 hash → API response mapping), skip re-processing identical cards

### Risk 3: New Card Layouts
**Mitigation:** Maintain layout detection model, add new layouts as discovered

---

## References & Resources

### Pokémon TCG Data Sources
- **Pokémon TCG API:** https://pokemontcg.io/ (for validation & fuzzy matching)
- **Bulbapedia Set List:** https://bulbapedia.bulbagarden.net/wiki/List_of_Pok%C3%A9mon_Trading_Card_Game_expansions
- **PkmnCards DB:** https://pkmncards.com/ (visual reference)

### OCR Libraries
- **EasyOCR:** https://github.com/JaidedAI/EasyOCR (better for stylized fonts)
- **Tesseract:** https://github.com/tesseract-ocr/tesseract (layout-based extraction)
- **OpenCV:** https://opencv.org/ (image preprocessing)

### Vision APIs (Comparison)
- **OpenAI GPT-4o-mini:** Current (good balance of cost/quality)
- **Anthropic Claude 3.5 Sonnet:** Higher accuracy, more expensive
- **Google Cloud Vision API:** Specialized OCR features
- **Azure Computer Vision:** Document intelligence features

---

**Next Steps:**
1. Review this proposal with stakeholders
2. Create test dataset (100 manually verified cards)
3. Implement Stage 1 extraction in parallel branch
4. Run comparison tests (v1.0 vs v2.0 Stage 1 only)
5. Iterate based on results

**Author:** Claude (with human review by Lucas Quiles)
**Status:** Awaiting approval to begin Phase 1 implementation
