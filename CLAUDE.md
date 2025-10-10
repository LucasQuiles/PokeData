# CLAUDE.md — PokeData AI Assistant Guide

**Version:** 1.0
**Last Updated:** 2025-10-09
**Purpose:** Enable efficient AI-assisted development and maintenance of the PokeData project

---

## 📚 Project Overview

**What This Is:**
PokeData is a production-grade OCR pipeline for extracting Pokémon Trading Card Game (TCG) card attributes from scanned images or PDFs. It combines local OCR (Tesseract), remote AI-powered OCR (OpenAI Vision API), and custom layout detection to provide accurate, structured data output.

**Core Architecture:**
- **Hybrid OCR Strategy:** Remote-first with local fallback for maximum accuracy and cost efficiency
- **Web + CLI Interface:** Flask web app for interactive use, Python CLI for batch processing
- **Structured Output:** CSV + JSON with confidence scoring and validation
- **Human-in-the-Loop:** Review dashboard for annotation and feedback collection

**Key Stakeholders:**
- Personal use case: Cataloging Pokémon card collections
- Future: Potential integration with collection management platforms, pricing APIs

---

## 📁 Project Structure & Navigation

### Directory Layout

```
PokeData/
├── pokedata                     # Primary entrypoint (Bash launcher)
├── app.py                       # Flask web application
├── pokedata.py                  # CLI script for terminal/batch processing
├── requirements.txt             # Python dependencies
│
├── pokedata_core/               # Core processing modules
│   ├── __init__.py              # Public API exports
│   ├── pipeline.py              # Main OCR & extraction (1200 lines)
│   ├── remote_ocr.py            # OpenAI Vision API integration (750 lines)
│   ├── region_cropper.py        # Layout detection & region extraction
│   ├── grading.py               # Card condition estimation
│   ├── annotation_model.py      # Layout model loading
│   ├── review_store.py          # Run storage and annotations
│   ├── logging_utils.py         # Centralized logging
│   ├── layouts.py               # Card layout definitions
│   └── schemas/
│       └── card_schema.json     # JSON schema for OpenAI Vision response
│
├── templates/                   # Flask Jinja2 templates
│   ├── index.html               # Upload interface
│   └── review.html              # Review dashboard
│
├── static/                      # CSS/JS for web UI
├── logs/                        # Application logs
├── Outputs/                     # Timestamped processing runs
├── .venv/                       # Auto-created virtual environment
└── .git/                        # Git repository
```

### Key Entry Points

1. **Web Interface:** `./pokedata` → Launches Flask on port 5000
2. **CLI Processing:** `python pokedata.py --input file.pdf --out results.csv`
3. **Direct API:** `from pokedata_core import process_to_csv`

---

## 🧠 Core Concepts & Terminology

### OCR Pipeline Terminology

| Term | Definition | Example |
|------|------------|---------|
| **Hybrid OCR** | Remote (OpenAI) first, local (Tesseract) fallback | Reduces API costs while maintaining accuracy |
| **Layout Detection** | Automatic card type identification | Pokémon vs Trainer vs Energy |
| **Region Cropping** | Extracting specific card sections | Title, HP, bottom text, abilities |
| **Confidence Scoring** | 0.0-1.0 score per extracted field | `{"name": 0.98, "hp": 0.87}` |
| **Fallback Suggestions** | Alternative values from other OCR methods | Stored in `notes.fallbackSuggestions` |
| **Validation Warnings** | Missing or malformed field alerts | `hp_missing`, `card_number_invalid` |

### Card Data Model

**CardRow** (CSV output columns):
- `source_image`, `page_index`, `page_sha1` — Tracking fields
- `card_type` — `pokemon`, `trainer`, `energy`, `unknown`
- `name`, `hp`, `evolves_from` — Basic identifiers
- `ability_name`, `ability_text` — Ability data
- `attacks` — JSON array of attack objects
- `set_name`, `set_code`, `card_number` — Set metadata
- `artist`, `weakness`, `resistance`, `retreat` — Additional attributes
- `notes` — JSON blob with layout, warnings, suggestions
- `rarity`, `quantity`, `est_grade` — Collection metadata
- `ocr_len`, `parse_warnings` — Quality metrics

**Structured JSON Payload** (from OpenAI Vision):
```json
{
  "name": "string",
  "stage": "Basic|Stage 1|Stage 2|...",
  "evolvesFrom": "string",
  "hp": integer,
  "types": ["Fire", "Water", ...],
  "text": {
    "abilities": [{"name": "...", "text": "...", "kind": "Ability"}],
    "attacks": [{"name": "...", "cost": ["Fire"], "damage": "120", "text": "..."}],
    "weaknesses": [{"type": "Water", "value": "×2"}],
    "resistances": [{"type": "Fighting", "value": "-30"}],
    "retreatCost": ["Colorless", "Colorless"]
  },
  "set": {"name": "...", "code": "OBF", "total": 197},
  "number": "12/197",
  "illustrator": "5ban Graphics",
  "notes": {"unreadable": ["/rarity"]},
  "_confidence": {"/name": 0.98, "/hp": 0.95}
}
```

### Card Types & Layout Logic

**Pokémon Cards:**
- Have valid HP (1-3 digits) OR attacks
- Exception: Technical Machines (TMs) are Trainers with attack text

**Trainer Cards:**
- No HP, no attacks
- Keywords: "Supporter", "Stadium", "Pokémon Tool", "Technical Machine"

**Energy Cards:**
- "Energy" in name
- No HP, no attacks

**Unknown:**
- Insufficient data to classify (flagged for review)

---

## 🔄 Processing Workflow

### High-Level Pipeline

```
1. Input Preparation
   ├─ PDF → Images (pdf2image via Poppler)
   └─ Image preprocessing (deskew, crop, enhance)

2. Layout Detection
   ├─ Detect card type (Pokémon/Trainer/Energy)
   └─ Crop specific regions (title, HP, footer, etc.)

3. OCR Extraction
   ├─ PRIMARY: OpenAI Vision API (structured JSON)
   ├─ FALLBACK: Tesseract OCR + regex parsing
   └─ HYBRID: Combine results, fill gaps

4. Field Normalization
   ├─ Text cleanup (unicode, punctuation)
   ├─ Validation (HP format, card number, set code)
   └─ Attack parsing (name, cost, damage, text)

5. Card Type Determination
   └─ Logic: HP present? Attacks? Keywords?

6. Output Generation
   ├─ CSV (one row per card)
   ├─ JSON (structured data + confidence)
   └─ Storage (Outputs/[timestamp]/)
```

### Remote OCR Integration (OpenAI Vision API)

**Key File:** `pokedata_core/remote_ocr.py`

**Strategy:**
1. **Multi-Crop Approach:** Send 4 images to Vision API
   - Full card image
   - Header crop (name, HP, type banner)
   - Middle crop (abilities, attacks, rules text)
   - Footer crop (set box, card number, artist, year)

2. **Structured Prompting:**
   - Explicit JSON schema instructions
   - Canonical energy type tokens (Colorless, Fire, Water, etc.)
   - Stage enumeration (Basic, Stage 1, Stage 2, etc.)
   - Unreadable field tracking (`notes.unreadable`)

3. **Response Handling:**
   - JSON parsing with fallback for code-block wrapped responses
   - Schema validation via `jsonschema`
   - Automatic payload repair for validation errors
   - Confidence score extraction (`_confidence` object)

4. **Error Recovery:**
   - Log invalid JSON to `logs/remote_debug/payload_*.json`
   - Normalize energy types (`"fire"` → `"Fire"`)
   - Repair schema violations (insert defaults)
   - Continue processing even with validation failures

**Environment Variables:**
- `POKEDATA_OPENAI_API_KEY` — Required for remote OCR
- `OPENAI_API_KEY` — Alternative key name (fallback)
- `POKEDATA_OPENAI_MODEL` — Model selection (default: `gpt-4o-mini`)
- `POKEDATA_REMOTE_OCR` — Enable/disable (`1`/`0`, default: `1`)
- `POKEDATA_REMOTE_CONFIDENCE_THRESHOLD` — Min confidence for fallback (default: `0.45`)

### Local OCR Fallback (Tesseract)

**Key File:** `pokedata_core/pipeline.py` (functions: `_ocr`, `parse_text_to_fields`)

**Strategy:**
1. **Full-Image OCR:** Tesseract with PSM 6 (uniform block)
2. **Regex Extraction:** Pattern matching for standard fields
   - HP: `\bHP\s*(\d{1,3})\b`
   - Card Number: `\b(\d{1,3}\s*/\s*\d{1,3})\b`
   - Artist: `\bIllus\.\s*([A-Za-z0-9'\-.\s]+)`
   - Attacks: `([A-Za-z][A-Za-z0-9'\- ]+?)\s+(\d{10,}|[1-9]\d{0,2}\+?)`

3. **Layout-Based Extraction:** Crop regions → OCR → extract
   - Uses `annotation_model.py` for predefined bounding boxes
   - Example: HP box at `{x: 0.85, y: 0.05, w: 0.1, h: 0.06}`

4. **Fallback Logic:**
   - Triggered when remote OCR fails OR fields missing/low-confidence
   - Results stored in `notes.fallbackSuggestions` if different from remote

---

## 🛠️ Technical Standards & Best Practices

### Code Organization

**Module Responsibilities:**
- `pipeline.py` — Core processing logic, field extraction, normalization
- `remote_ocr.py` — OpenAI API integration, schema validation, payload repair
- `region_cropper.py` — Image cropping, layout detection, region-specific OCR
- `grading.py` — Visual condition assessment (edge wear, scratches, centering)
- `review_store.py` — Run storage, annotation persistence, low-confidence queries
- `logging_utils.py` — Centralized logging configuration

**Separation of Concerns:**
- Flask app (`app.py`) handles HTTP routes, file uploads, session management
- CLI script (`pokedata.py`) provides argparse interface for terminal use
- Launcher (`pokedata`) handles dependency checks, virtualenv, port cleanup

### Naming Conventions

**Functions:**
- Public API: `snake_case` without underscore prefix (e.g., `process_to_csv`)
- Private helpers: `_snake_case` with leading underscore (e.g., `_normalize_text`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `MAX_OCR_CHARS`, `REMOTE_OCR_ENABLED`)

**Variables:**
- Local variables: `snake_case`
- Type hints: Use `typing` module (`Dict[str, Any]`, `Optional[str]`)
- Dataclass fields: `snake_case` matching CSV column names

**Files:**
- Python modules: `snake_case.py`
- Config files: `lowercase.txt`, `lowercase.json`
- Documentation: `UPPERCASE.md` for repo-level, `lowercase.md` for guides

### Error Handling Philosophy

**Defensive Programming:**
- Assume remote OCR can fail (API limits, network issues)
- Assume Tesseract can fail (missing dependency, unsupported language)
- Assume images can be malformed (corrupt PDFs, unsupported formats)

**Graceful Degradation:**
```python
try:
    fields = extract_card_fields(pil_img)  # Remote OCR
    remote_used = True
except Exception as exc:
    warnings.append(f"remote_error:{exc}")
    # Fall back to local OCR
    text = _ocr(pil_img)
    fields = parse_text_to_fields(text)
    remote_used = False
```

**Logging Levels:**
- `logger.debug()` — Verbose processing details (OCR text, crop dimensions)
- `logger.info()` — Processing milestones (file processed, CSV written)
- `logger.warning()` — Recoverable issues (schema validation failed, missing deps)
- `logger.exception()` — Unrecoverable errors (file not found, critical failures)

### Logging Best Practices

**Location:** `logs/pokedata.log` (rotating file handler)

**Format:** `%(asctime)s - %(name)s - %(levelname)s - %(message)s`

**Usage:**
```python
from pokedata_core.logging_utils import get_logger

logger = get_logger("module_name")
logger.info("Processing %s (%d pages)", filename, page_count)
logger.warning("Remote OCR failed for %s: %s", image_name, exc)
logger.exception("Critical failure in %s", function_name)
```

**Debug Dumps:**
- Invalid JSON → `logs/remote_debug/payload_*.json`
- Schema violations → `logs/remote_debug/payload_*.json`

---

## 🔐 Security & Privacy Considerations

### API Key Management

**Current Practice:**
- Environment variable `POKEDATA_OPENAI_API_KEY`
- Never commit API keys to Git
- Launcher checks for key before remote OCR

**Best Practice Recommendations:**
- Use `.env` file with `python-dotenv` for local development
- Add `.env` to `.gitignore`
- Document required keys in README

### Data Privacy

**User Uploads:**
- Stored temporarily during processing (tmpdir with cleanup)
- Results saved to `Outputs/[timestamp]/` unless deleted
- No automatic cloud upload (local-first)

**Remote OCR:**
- Card images sent to OpenAI Vision API (base64 encoded)
- Review OpenAI's data usage policies if handling sensitive collections
- Option to disable remote OCR: `export POKEDATA_REMOTE_OCR=0`

---

## 🧪 Testing & Quality Assurance

### Manual Testing Checklist

**Web Interface:**
1. Upload PDF → verify CSV download
2. Upload image → verify processing
3. Review dashboard → verify past runs load
4. Low-confidence items → verify threshold filtering
5. Annotations → verify save/load

**CLI:**
1. Process single PDF → verify CSV output
2. Process image folder → verify multiple rows
3. Limit pages → verify limit respected
4. Custom DPI → verify image quality

**Error Scenarios:**
1. Invalid file format → user-friendly error
2. Missing Poppler → installation instructions
3. Missing Tesseract → graceful degradation
4. Invalid OpenAI key → clear error message

### Release Gate Protocol

**From AGENTS.md:**

1. **Launcher Syntax Integrity:**
   ```bash
   ./pokedata --help
   ```
   Must execute without syntax errors.

2. **Dependency Self-Test:**
   ```bash
   ./pokedata --no-browser
   ```
   Must launch successfully, auto-installing missing dependencies.

3. **Regression Testing:**
   - Process sample PDF
   - Verify CSV structure
   - Check web UI workflow
   - Validate review dashboard

### Common Issues & Resolutions

| Issue | Cause | Fix |
|-------|-------|-----|
| Port 5000 in use | Previous instance running | `lsof -ti tcp:5000 \| xargs kill` |
| Poppler not found | Missing dependency | `brew install poppler` |
| Tesseract not found | Missing dependency | `brew install tesseract` |
| OpenAI API error | Invalid/missing key | `export POKEDATA_OPENAI_API_KEY="sk-..."` |
| PDF conversion fails | Poppler not in PATH | Launcher auto-adds common paths |
| Schema validation fails | API response format changed | Payload logged to `logs/remote_debug/` |

---

## 🎯 Development Workflows

### Adding a New Field

**Example: Adding "Rarity" Field**

1. **Update `CardRow` dataclass** (`pipeline.py:421-446`):
   ```python
   @dataclass
   class CardRow:
       # ... existing fields ...
       rarity: str = ""
   ```

2. **Update JSON schema** (`schemas/card_schema.json`):
   ```json
   "rarity": {
     "type": "string",
     "description": "Rarity symbol or text"
   }
   ```

3. **Update remote OCR mapping** (`remote_ocr.py:195-212`):
   ```python
   fields = {
       # ... existing mappings ...
       "rarity": str(data.get("rarity", "")),
   }
   ```

4. **Update local OCR extraction** (`pipeline.py:635-687`):
   ```python
   def parse_text_to_fields(raw_text: str) -> Tuple[Dict[str, str], List[str]]:
       # ... existing logic ...
       out["rarity"] = extract_rarity_from_text(text)
   ```

5. **Update normalization** (`pipeline.py:240-297`):
   ```python
   text_keys = {
       # ... existing keys ...
       "rarity",
   }
   ```

### Modifying OpenAI Prompt

**Location:** `remote_ocr.py:56-111` (`_build_prompt` function)

**Guidelines:**
- Keep instructions explicit and detailed
- Provide schema skeleton example
- Define canonical tokens (energy types, stages)
- Specify handling of unreadable fields
- Test with sample cards before deploying

**Example Modification:**
```python
instructions = (
    "You are a meticulous Pokémon card transcriber. "
    "NEW INSTRUCTION: If the card shows a holographic pattern, set notes.holographic=true. "
    "Always respond with a single JSON object..."
)
```

### Tuning Confidence Thresholds

**Remote OCR Confidence:**
- `POKEDATA_REMOTE_CONFIDENCE_THRESHOLD` (default: `0.45`)
- Fields below threshold trigger local OCR fallback
- Location: `pipeline.py:69-73`

**Review Dashboard Threshold:**
- `POKEDATA_CONFIDENCE_THRESHOLD` (default: `0.9`)
- Controls low-confidence item filtering
- Location: `app.py:182`

**Recommendation:**
- Lower remote threshold (0.3-0.5) → More fallback attempts
- Higher review threshold (0.85-0.95) → Stricter quality control

---

## 🚀 Deployment & Scaling Considerations

### Current Limitations

- **Single-Threaded:** Processes one card at a time
- **Local Storage:** Outputs saved to disk (not cloud)
- **No Authentication:** Web UI is open (designed for localhost)
- **No Database:** Uses file-based storage for runs

### Future Enhancements (Potential)

1. **Parallel Processing:**
   - Use `concurrent.futures` for multi-card PDFs
   - Batch OpenAI API calls

2. **Cloud Storage:**
   - S3/GCS for Outputs and images
   - PostgreSQL for run metadata

3. **Authentication:**
   - Flask-Login for multi-user support
   - API keys for programmatic access

4. **Real-Time Collaboration:**
   - WebSocket for live annotation sessions
   - Shared review queues

5. **Training Data Collection:**
   - Export human feedback for model fine-tuning
   - Continual learning from corrections

---

## 📊 Metrics & Monitoring

### Processing Metrics

**Tracked in CSV:**
- `ocr_len` — OCR text length (chars) → Quality indicator
- `parse_warnings` — Comma-separated warning codes → Error tracking
- `page_sha1` — Image hash → Duplicate detection

**Logged Metrics:**
- Processing time per card (not currently tracked — potential addition)
- Remote vs local OCR usage ratio
- Validation error frequency

### Quality Indicators

**High Quality:**
- `ocr_len > 500` (sufficient text extracted)
- `parse_warnings` empty or minimal
- All required fields present (`name`, `card_number`, `artist`)

**Low Quality / Review Needed:**
- `parse_warnings` contains `hp_missing`, `name_guess_failed`, `artist_missing`
- Remote OCR `_confidence` scores < 0.9
- `notes.remoteWarnings.unreadable` contains fields

---

## 🤝 Contributing Guidelines

### Before Making Changes

1. **Read AGENTS.md:** Understand release gate requirements
2. **Run existing tests:** `./pokedata --help` and `./pokedata --no-browser`
3. **Check logs:** Review `logs/pokedata.log` for baseline behavior

### Code Style

- **PEP 8 Compliance:** Use `flake8` or `black` formatter
- **Type Hints:** Add where practical (function signatures minimum)
- **Docstrings:** Public functions and modules (Google style)

**Example:**
```python
def process_to_csv(
    input_path: Path, out_csv: Path, *, limit: int = 0, dpi: int = 300
) -> ProcessResult:
    """Process input file/folder and write results to CSV.

    Args:
        input_path: PDF file or directory of images.
        out_csv: Output CSV file path.
        limit: Maximum pages/images to process (0 = all).
        dpi: DPI for PDF to image conversion.

    Returns:
        ProcessResult with rows, images, and CSV path.

    Raises:
        RuntimeError: If dependencies (Poppler, pdf2image) missing.
        FileNotFoundError: If input_path doesn't exist.
    """
```

### Commit Messages

**Format:**
```
<type>: <short summary>

<detailed description>

<optional footer>
```

**Types:**
- `feat:` — New feature
- `fix:` — Bug fix
- `refactor:` — Code restructuring (no behavior change)
- `docs:` — Documentation only
- `test:` — Testing improvements
- `chore:` — Build/tooling changes

**Examples:**
```
feat: Add rarity field extraction from card footer

- Update CardRow dataclass with rarity field
- Add regex pattern for rarity symbols
- Map rarity from OpenAI Vision response
- Update CSV output to include new column

Closes #42
```

```
fix: Handle edge case for cards with no HP text

Previously crashed when processing Energy cards.
Now gracefully handles missing HP via layout detection.

Fixes #38
```

### Pull Request Checklist

- [ ] Release gates pass (`./pokedata --help`, `./pokedata --no-browser`)
- [ ] Manual testing completed (web + CLI workflows)
- [ ] Logs reviewed for new warnings/errors
- [ ] README updated if user-facing changes
- [ ] CLAUDE.md updated if architecture changes
- [ ] Commit messages follow format
- [ ] No API keys or secrets committed

---

## 📖 Additional Resources

### External Documentation

- **Tesseract OCR:** https://github.com/tesseract-ocr/tesseract
- **Poppler:** https://poppler.freedesktop.org/
- **OpenAI Vision API:** https://platform.openai.com/docs/guides/vision
- **Flask:** https://flask.palletsprojects.com/
- **Pillow:** https://pillow.readthedocs.io/
- **jsonschema:** https://python-jsonschema.readthedocs.io/

### Project-Specific Docs

- **[README.md](README.md)** — User-facing documentation
- **[AGENTS.md](AGENTS.md)** — Release gate protocols
- **[requirements.txt](requirements.txt)** — Python dependencies

### Pokémon TCG References

- **Card Database:** https://www.pokemontcg.io/
- **Set Codes:** https://bulbapedia.bulbagarden.net/wiki/List_of_Pok%C3%A9mon_Trading_Card_Game_expansions
- **Energy Types:** https://bulbapedia.bulbagarden.net/wiki/Type_(TCG)

---

## 🔮 Future Considerations

### Potential Improvements

1. **Machine Learning Enhancements:**
   - Fine-tune custom OCR model on Pokémon cards
   - Train layout detector on larger dataset
   - Build confidence predictor from human feedback

2. **Integration Opportunities:**
   - TCGPlayer API for pricing data
   - Collection management platforms (TCG Hub, Dragon Shield)
   - Automated eBay/marketplace listing generation

3. **Performance Optimizations:**
   - Cache OpenAI API responses (SHA1 hash → response mapping)
   - Parallel processing for multi-card PDFs
   - GPU acceleration for image preprocessing

4. **User Experience:**
   - Real-time progress indicators
   - Drag-and-drop region correction
   - Bulk edit interface for common corrections

### Known Limitations

- **Vintage Cards:** Pre-2000 cards have inconsistent layouts (limited testing)
- **Foil/Holo Cards:** Reflections can confuse OCR
- **Non-English Cards:** Schema assumes English text (would need i18n)
- **Jumbo/Promo Cards:** Non-standard dimensions may crop incorrectly

---

## 📐 Code Quality Principles

### DRY (Don't Repeat Yourself)

**Identify Repetition:**
```python
# ❌ BAD: Repeated normalization logic
fields["name"] = data.get("name", "").strip()
fields["artist"] = data.get("artist", "").strip()
fields["set_name"] = data.get("set_name", "").strip()

# ✅ GOOD: Extracted helper function
def _normalize_text(value: str) -> str:
    """Normalize text by stripping whitespace and standardizing unicode."""
    if not value:
        return ""
    return ud.normalize("NFKC", value).strip()

fields["name"] = _normalize_text(data.get("name"))
fields["artist"] = _normalize_text(data.get("artist"))
fields["set_name"] = _normalize_text(data.get("set_name"))
```

**Reusable Patterns:**
- Extract regex patterns to module-level constants (`RE_HP`, `RE_CARDNUM`)
- Create utility functions for common operations (`_clean_str`, `_canonical_type`)
- Use decorators for cross-cutting concerns (logging, timing, caching)

### SOLID Principles Applied

**Single Responsibility:**
- `pipeline.py` — Core extraction logic only
- `remote_ocr.py` — OpenAI API integration only
- `review_store.py` — Storage and retrieval only

**Open/Closed:**
- New card layouts? Add to `layouts.py` without modifying `pipeline.py`
- New OCR providers? Implement interface without changing calling code

**Dependency Inversion:**
- High-level modules (`app.py`) depend on abstractions (`process_to_csv`)
- Low-level modules (`remote_ocr.py`) implement interfaces

### Modular Design Checklist

- [ ] **Function length:** Max 50 lines per function (exceptions allowed)
- [ ] **Module cohesion:** Related functions grouped together
- [ ] **Loose coupling:** Modules communicate via well-defined interfaces
- [ ] **Clear boundaries:** Public API in `__init__.py`, private helpers prefixed with `_`
- [ ] **Composability:** Small functions that combine to solve complex tasks

**Example of Good Modularity:**
```python
# High-level orchestration
def process_page(image_path: Path, index: int) -> Tuple[CardRow, Optional[Dict]]:
    pil = _load_and_preprocess(image_path)
    crops = _detect_and_crop_regions(pil)
    fields = _extract_fields_hybrid(pil, crops)
    row = _build_card_row(fields, image_path, index)
    return row, fields.get("_structured_raw")

# Each helper is focused and testable
def _load_and_preprocess(image_path: Path) -> Image.Image:
    """Load image and apply preprocessing (deskew, crop, enhance)."""
    pil = Image.open(image_path).convert("RGB")
    pil = _cv2_deskew_if_available(pil)
    pil = _auto_crop_card_if_available(pil)
    return _pil_enhance(pil)
```

### Maintainability Best Practices

**1. Clear Naming:**
```python
# ❌ BAD: Cryptic names
def proc(d, t): ...
x = parse(img)
RE_P = re.compile(r"\d+")

# ✅ GOOD: Descriptive names
def process_card_image(image_data: bytes, threshold: float) -> Dict[str, str]: ...
extracted_fields = parse_ocr_text(card_image)
RE_CARD_NUMBER = re.compile(r"\b(\d{1,3}\s*/\s*\d{1,3})\b")
```

**2. Intentional Comments:**
```python
# ❌ BAD: Obvious comment
# Increment i
i += 1

# ❌ BAD: Commented-out code (use git history instead)
# old_value = data.get("hp", 0)
new_value = data.get("hp", "")

# ✅ GOOD: Why not what
# Technical Machines are Trainers with attack text; exclude from Pokémon classification
if _looks_like_technical_machine(name, structured):
    return CARD_TYPE_TRAINER

# ✅ GOOD: Complex logic explanation
# OpenAI may return unreadable field pointers like "/set/code" or "text.attacks[0].name"
# We normalize these to our field names ("set_code", "attacks") for fallback lookup
for pointer in notes_obj.get("unreadable", []):
    mapped_field = _remote_pointer_to_field(pointer)
```

**3. Comprehensive Docstrings:**
```python
def extract_card_fields(pil_image: Image.Image) -> Dict[str, str]:
    """Extract Pokémon card fields using OpenAI Vision API.

    Sends four cropped views of the card (full, header, middle, footer) to
    the Vision API with structured JSON schema prompting. Validates the
    response against card_schema.json and attempts automatic repair of
    validation errors.

    Args:
        pil_image: PIL Image object of the card face (RGB mode).

    Returns:
        Dictionary mapping field names to extracted values:
            - Standard fields: name, hp, artist, card_number, set_code, etc.
            - Special keys:
                - "_structured_raw": Full JSON response from OpenAI
                - "_remote_validation_errors": List of schema violations (if any)

    Raises:
        RuntimeError: If POKEDATA_OPENAI_API_KEY environment variable not set.
        ValueError: If API returns non-JSON or unparseable response.

    Example:
        >>> img = Image.open("charizard.png")
        >>> fields = extract_card_fields(img)
        >>> fields["name"]
        'Charizard ex'
        >>> fields["hp"]
        '180'
    """
```

**4. Change Log Discipline:**

**Location:** Track in `CHANGELOG.md` (create if doesn't exist)

**Format (Keep a Changelog standard):**
```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- Rarity field extraction from card footer region
- Confidence threshold tuning via environment variable

### Changed
- Improved HP detection accuracy by adding layout-based fallback
- Updated OpenAI Vision prompt to explicitly request rarity symbol

### Fixed
- Energy cards no longer incorrectly flagged as missing HP
- Card number regex now handles trainer gallery cards (TG01/TG30)

### Deprecated
- Direct OPENAI_API_KEY usage (use POKEDATA_OPENAI_API_KEY instead)

## [1.0.0] - 2025-10-09
### Added
- Initial release with hybrid OCR pipeline
- Web interface for upload and review
- CLI for batch processing
- OpenAI Vision API integration
```

**When to Update:**
- **Every commit:** Add to `[Unreleased]` section
- **Every release:** Move `[Unreleased]` → `[X.Y.Z]` with date
- **Breaking changes:** Note in `### Breaking Changes` subsection

### Readable Code Standards

**1. Vertical Spacing:**
```python
# ✅ GOOD: Grouped related logic, separated by blank lines
def process_page(image_path: Path, index: int) -> Tuple[CardRow, Optional[Dict]]:
    # Load and preprocess
    pil = Image.open(image_path).convert("RGB")
    pil = _cv2_deskew_if_available(pil)
    pil = _pil_enhance(pil)

    # Extract fields via remote OCR
    try:
        fields = extract_card_fields(pil)
        remote_used = True
    except Exception as exc:
        logger.warning("Remote OCR failed: %s", exc)
        fields = {}
        remote_used = False

    # Build final row
    row = CardRow(
        source_image=str(image_path),
        page_index=index,
        **fields,
    )

    return row, fields.get("_structured_raw")
```

**2. Guard Clauses (Early Returns):**
```python
# ❌ BAD: Deep nesting
def validate_field(value, field_type):
    if value is not None:
        if field_type == "hp":
            if RE_VALID_HP.fullmatch(value):
                return value
            else:
                return ""
        else:
            return value
    else:
        return ""

# ✅ GOOD: Early returns reduce nesting
def validate_field(value: Optional[str], field_type: str) -> str:
    """Validate field value based on type-specific rules."""
    if value is None:
        return ""

    if field_type != "hp":
        return value

    if RE_VALID_HP.fullmatch(value):
        return value

    return ""
```

**3. Meaningful Variable Names:**
```python
# ❌ BAD: Single-letter variables for non-trivial logic
for i in data:
    x = i.get("name")
    if x:
        y.append(x)

# ✅ GOOD: Descriptive names
for attack in attack_data:
    attack_name = attack.get("name")
    if attack_name:
        attack_names.append(attack_name)

# ✅ ACCEPTABLE: Loop counters when scope is tiny
for i in range(3):
    retry_operation(i)
```

### Efficient Code Guidelines

**1. Lazy Evaluation:**
```python
# ❌ BAD: Always executes expensive operation
full_ocr_text = _ocr(pil_img)  # Expensive!
if remote_used and all_fields_present:
    return fields  # Didn't need OCR after all

# ✅ GOOD: Only compute when needed
if not remote_used or missing_fields:
    full_ocr_text = _ocr(pil_img)
    fallback_fields = parse_text_to_fields(full_ocr_text)
```

**2. Caching Expensive Operations:**
```python
# ❌ BAD: Re-computes layout extraction every time
def ensure_crops() -> Optional[CroppedRegions]:
    return crop_regions(pil, detect_layout(pil))  # Re-runs detection!

# ✅ GOOD: Cache the result
def ensure_crops() -> Optional[CroppedRegions]:
    nonlocal crops, layout_id
    if crops is not None:
        return crops  # Cached

    layout_id = detect_layout(pil)
    crops = crop_regions(pil, layout_id)
    return crops
```

**3. Batch Operations:**
```python
# ❌ BAD: N API calls for N cards
for card_image in card_images:
    result = openai_api.extract_fields(card_image)
    results.append(result)

# ✅ BETTER: Batch API calls (if API supports)
# Note: Current OpenAI Vision API doesn't support batching,
# but this is the pattern to follow when available
batch_results = openai_api.extract_fields_batch(card_images)
```

**4. Avoid Premature Optimization:**
```python
# ❌ BAD: Micro-optimization that hurts readability
def parse(t):
    return (m.group(1) if (m := RE_HP.search(t)) else "", ...)

# ✅ GOOD: Clear and maintainable (fast enough)
def parse_text_to_fields(text: str) -> Tuple[Dict[str, str], List[str]]:
    """Extract fields from OCR text using regex patterns.

    Performance: ~5ms per card on average hardware.
    """
    hp_match = RE_HP.search(text)
    hp_value = hp_match.group(1) if hp_match else ""
    # ... rest of extraction
    return fields, warnings
```

**Optimization Priority:**
1. **Correctness** — Does it work?
2. **Readability** — Can others understand it?
3. **Maintainability** — Can it be modified safely?
4. **Performance** — Is it fast enough?

Only optimize for performance when profiling shows a bottleneck.

### Testing Mindset

**Write Testable Code:**
```python
# ❌ BAD: Hard to test (depends on filesystem, global state)
def process():
    with open("config.json") as f:
        config = json.load(f)
    client = OpenAI(api_key=os.getenv("API_KEY"))
    return client.process(config["model"])

# ✅ GOOD: Dependency injection makes testing easy
def process(config_path: Path, api_key: str, model: str) -> Result:
    """Process using provided configuration and credentials.

    Args:
        config_path: Path to configuration file.
        api_key: OpenAI API key.
        model: Model name to use.

    Returns:
        Processing result.
    """
    with config_path.open() as f:
        config = json.load(f)
    client = OpenAI(api_key=api_key)
    return client.process(model)
```

**Manual Testing Checklist** (until automated tests added):
- [ ] Happy path (valid PDF → CSV with correct data)
- [ ] Edge cases (0-page PDF, corrupted image, missing fields)
- [ ] Error paths (invalid API key, missing dependencies)
- [ ] Performance (10-page PDF processes in <30s)

---

## 🎓 Learning Path for New Contributors

### Beginner (Understanding the System)

1. Read README.md → Understand user-facing features
2. Run `./pokedata` → Experience web interface
3. Process sample PDF → Observe CSV output
4. Review `logs/pokedata.log` → See processing flow

### Intermediate (Code Exploration)

1. Read `pipeline.py` → Understand core logic
2. Read `remote_ocr.py` → Understand OpenAI integration
3. Trace a single card through the pipeline (add debug prints)
4. Experiment with confidence thresholds

### Advanced (Contributing Features)

1. Read AGENTS.md → Understand quality gates
2. Study JSON schema → Understand structured data model
3. Review `region_cropper.py` → Understand layout detection
4. Propose and implement a new feature

---

**Last Updated:** 2025-10-09
**Maintained by:** Lucas Quiles
**For AI Assistants:** This document provides context for code generation, debugging, and feature development on the PokeData project.

---

## 🤖 AI Assistant Protocols

### When Generating Code

1. **Follow existing patterns:** Match style in similar functions
2. **Add type hints:** Function signatures minimum
3. **Include docstrings:** Especially for public APIs
4. **Handle errors gracefully:** Try/except with logging
5. **Test changes manually:** Run launcher and CLI

### When Reviewing Code

1. **Check release gates:** Verify launcher syntax
2. **Validate schemas:** Ensure JSON schema compatibility
3. **Review logs:** Look for new warnings
4. **Test edge cases:** Empty fields, malformed input
5. **Document changes:** Update README/CLAUDE.md if needed

### When Debugging

1. **Check logs first:** `tail -f logs/pokedata.log`
2. **Review debug payloads:** `logs/remote_debug/payload_*.json`
3. **Test in isolation:** Single card, single function
4. **Reproduce reliably:** Identify minimal failing case
5. **Fix root cause:** Don't just patch symptoms

### Communication Best Practices

- **Be specific:** "HP extraction fails for Energy cards" not "OCR broken"
- **Provide context:** Include log snippets, error messages
- **Reference code:** Use file:line format (e.g., `pipeline.py:1034`)
- **Suggest solutions:** Not just identify problems
- **Update docs:** Keep CLAUDE.md current with architecture changes
