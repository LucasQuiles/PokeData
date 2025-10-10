# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- Nothing currently in development

### Changed
- Nothing currently in development

### Fixed
- Nothing currently in development

---

## [1.0.0] - 2025-10-09

### Added
- **Core OCR Pipeline**
  - Hybrid OCR strategy (OpenAI Vision API primary, Tesseract fallback)
  - Multi-crop image submission (full, header, middle, footer regions)
  - Structured JSON schema validation against `card_schema.json`
  - Confidence scoring per field (0.0-1.0 scale)
  - Automatic layout detection (Pokémon/Trainer/Energy cards)

- **Web Interface** (`app.py`)
  - Flask web application with upload and processing routes
  - Interactive review dashboard for low-confidence items
  - Run history tracking with timestamped storage
  - Annotation support for human feedback collection
  - Real-time processing with progress feedback

- **CLI Interface** (`pokedata.py`)
  - Command-line batch processing support
  - Configurable DPI for PDF conversion
  - Page limit controls for testing
  - Direct CSV output generation

- **Bash Launcher** (`./pokedata`)
  - Automatic dependency checking and installation
  - Virtual environment management (.venv auto-creation)
  - Port cleanup (kills processes on port 5000)
  - Graceful shutdown with signal handling
  - Auto-installation of Poppler and Tesseract via Homebrew

- **OpenAI Vision Integration** (`remote_ocr.py`)
  - GPT-4o-mini model for card field extraction
  - Structured prompting with canonical tokens
  - JSON Schema Draft 2020-12 validation
  - Automatic payload repair for validation errors
  - Debug logging for invalid responses (`logs/remote_debug/`)
  - Configurable confidence thresholds

- **Local OCR Fallback** (`pipeline.py`)
  - Tesseract OCR integration with PSM 6 mode
  - Regex-based field extraction (HP, card number, artist, attacks)
  - Layout-based region extraction via `annotation_model.py`
  - Fallback suggestions stored in notes field

- **Data Processing**
  - `CardRow` dataclass with 26 fields (name, HP, attacks, set info, etc.)
  - CSV output with one row per card
  - JSON output with structured data and confidence scores
  - SHA1 image hashing for duplicate detection
  - Warning and validation tracking

- **Image Processing**
  - PDF to image conversion via `pdf2image` (Poppler backend)
  - Image preprocessing (deskew, crop, enhance) via OpenCV
  - Region-specific cropping for targeted OCR
  - Support for multi-page PDFs

- **Documentation**
  - Comprehensive README.md with installation, usage, troubleshooting
  - CLAUDE.md AI assistant guide with coding standards
  - AGENTS.md release gate protocols
  - Inline code documentation with Google-style docstrings

- **Quality Assurance**
  - Release gate protocol (syntax check, dependency self-test)
  - Centralized logging via `logging_utils.py`
  - Error recovery with graceful degradation
  - Debug payload dumps for troubleshooting

### Technical Details

**Dependencies:**
- Flask 3.0+ (web framework)
- OpenAI 2.1.0+ (Vision API client)
- pytesseract (local OCR)
- Pillow (image processing)
- pdf2image (PDF conversion)
- opencv-python (image preprocessing)
- numpy (numerical operations)
- jsonschema 4.22+ (schema validation)
- easyocr (advanced OCR fallback)
- requests (HTTP client)

**Environment Variables:**
- `POKEDATA_OPENAI_API_KEY` — OpenAI API key (required for remote OCR)
- `POKEDATA_OPENAI_MODEL` — Model selection (default: gpt-4o-mini)
- `POKEDATA_REMOTE_OCR` — Enable/disable remote OCR (default: 1)
- `POKEDATA_REMOTE_CONFIDENCE_THRESHOLD` — Min confidence (default: 0.45)
- `POKEDATA_CONFIDENCE_THRESHOLD` — Review dashboard threshold (default: 0.9)

**File Structure:**
```
PokeData/
├── pokedata                    # Bash launcher (primary entrypoint)
├── app.py                      # Flask web application
├── pokedata.py                 # CLI script
├── requirements.txt            # Python dependencies
├── README.md                   # User documentation
├── CLAUDE.md                   # AI assistant guide
├── AGENTS.md                   # Release gate protocols
├── CHANGELOG.md                # This file
├── pokedata_core/              # Core processing modules
│   ├── pipeline.py             # Main OCR & extraction logic
│   ├── remote_ocr.py           # OpenAI Vision API integration
│   ├── region_cropper.py       # Layout detection & cropping
│   ├── grading.py              # Card condition estimation
│   ├── annotation_model.py     # Layout model definitions
│   ├── review_store.py         # Run storage and annotations
│   ├── logging_utils.py        # Centralized logging
│   ├── layouts.py              # Card layout specifications
│   └── schemas/
│       └── card_schema.json    # JSON schema for Vision API
├── templates/                  # Flask Jinja2 templates
│   ├── index.html              # Upload interface
│   └── review.html             # Review dashboard
├── static/                     # CSS/JS for web UI
├── logs/                       # Application logs
├── Outputs/                    # Timestamped processing runs
└── .venv/                      # Auto-created virtualenv
```

**Known Limitations:**
- Single-threaded processing (one card at a time)
- Local storage only (no cloud integration)
- No authentication (designed for localhost use)
- File-based run storage (no database)
- Limited testing on vintage/non-English cards

**Platform Requirements:**
- Python 3.9+
- macOS (Homebrew for dependencies) or Linux
- Poppler (for PDF conversion)
- Tesseract (for local OCR)
- Internet connection (for OpenAI API)

---

## Release Notes

### What's New in 1.0.0

This is the initial production release of PokeData, a Pokémon Trading Card Game OCR pipeline. The system combines cutting-edge AI (OpenAI Vision API) with traditional OCR (Tesseract) to extract card attributes from scanned images and PDFs.

**Key Features:**
- 📸 **Hybrid OCR** — AI-first with local fallback for maximum accuracy
- 🌐 **Web Interface** — Upload, process, and review cards in your browser
- ⚡ **CLI Support** — Batch processing for large collections
- 🎯 **High Accuracy** — Multi-crop strategy + structured JSON schema
- 📊 **Confidence Scoring** — Know which fields need human review
- 🔄 **Auto-Setup** — Launcher handles all dependency installation

**Getting Started:**
```bash
# Clone repository and navigate to directory
cd PokeData

# Set OpenAI API key
export POKEDATA_OPENAI_API_KEY="sk-..."

# Launch web interface (auto-installs dependencies)
./pokedata

# Or process via CLI
python pokedata.py --input cards.pdf --out results.csv
```

**What's Next:**
- Parallel processing for multi-card PDFs
- Cloud storage integration (S3/GCS)
- Authentication for multi-user support
- Fine-tuned OCR model for vintage cards
- Integration with pricing APIs (TCGPlayer)

---

## Previous Versions

### [0.9.0] - 2025-10-05 (Beta)
- Initial beta release with core functionality
- Limited testing and documentation

### [0.5.0] - 2025-09-28 (Alpha)
- Early prototype with basic OCR capabilities

---

## Contributing

When making changes:
1. Update `[Unreleased]` section with your changes
2. Follow format: `### Added/Changed/Fixed/Deprecated/Removed`
3. Include descriptive bullet points with context
4. Reference issue/PR numbers where applicable
5. Keep entries in reverse chronological order (newest first)

On release:
1. Move `[Unreleased]` content to new version section
2. Add release date in ISO format (YYYY-MM-DD)
3. Create git tag: `git tag -a v1.0.0 -m "Release 1.0.0"`
4. Update version in documentation and code

---

**Maintained by:** Lucas Quiles
**Project Repository:** /Users/lucas/SNEKOPS/PokeData
**Documentation:** See [README.md](README.md) and [CLAUDE.md](CLAUDE.md)
