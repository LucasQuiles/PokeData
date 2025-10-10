# PokeData — Pokémon TCG Card OCR & Cataloging Tool

**Version:** 1.0
**Last Updated:** 2025-10-09
**Repository:** https://github.com/LucasQuiles/PokeData

---

## 📖 Overview

PokeData is an intelligent OCR (Optical Character Recognition) system designed to extract and catalog Pokémon Trading Card Game (TCG) card details from scanned images or PDFs. The tool combines local OCR (Tesseract), remote AI-powered OCR (OpenAI Vision API), and custom layout detection to accurately identify card attributes like name, HP, attacks, abilities, set information, and rarity.

**Core Value:** Automate the tedious process of manually cataloging Pokémon card collections—scan a binder page or bulk collection PDF, and get structured CSV/JSON data ready for spreadsheets, databases, or collection management tools.

---

## ✨ Key Features

### OCR & Data Extraction
- **Hybrid OCR Pipeline:** Combines Tesseract (local) and OpenAI Vision API (remote) for maximum accuracy
- **Layout Detection:** Automatically identifies Pokémon, Trainer, and Energy card layouts
- **Field Extraction:** Name, HP, evolves from, abilities, attacks, weakness, resistance, retreat cost, set code, card number, artist, rarity
- **Image Preprocessing:** Auto-deskew, edge detection, card cropping, contrast enhancement
- **Grading Estimation:** Automatic visual grade estimation based on card condition

### Web Interface
- **Upload & Process:** Drag-and-drop PDF or image files, configure DPI and page limits
- **Review Dashboard:** Browse past processing runs, view extracted data, annotate low-confidence fields
- **Human-in-the-Loop:** Flag and correct OCR errors, provide feedback for future training
- **CSV Download:** Instantly download processed results as CSV

### Command-Line Interface
- **Batch Processing:** Process entire folders or multi-page PDFs from the terminal
- **Scriptable:** Integrate into automation workflows
- **JSON Output:** Structured JSON export alongside CSV for advanced integrations

### Quality & Validation
- **Confidence Scoring:** Each field gets a confidence score; low-confidence items flagged for review
- **Fallback Strategies:** Multiple OCR attempts with different preprocessing techniques
- **Validation Warnings:** Alerts for missing or invalid fields (e.g., malformed HP, card numbers)
- **Logging:** Comprehensive debug logs for troubleshooting (`logs/pokedata.log`)

---

## 🗂️ Project Structure

```
PokeData/
├── README.md                  # This file
├── CLAUDE.md                  # AI assistant guide (coding standards & architecture)
├── CHANGELOG.md               # Version history and release notes
├── AGENTS.md                  # Release gates and agent protocols
├── requirements.txt           # Python dependencies
├── pokedata                   # Launcher script (bash) — primary entrypoint
├── pokedata.py                # CLI script for terminal usage
├── app.py                     # Flask web application
│
├── pokedata_core/             # Core processing modules
│   ├── pipeline.py            # Main OCR & extraction logic
│   ├── remote_ocr.py          # OpenAI Vision API integration
│   ├── region_cropper.py      # Layout detection & region extraction
│   ├── grading.py             # Card condition grading
│   ├── annotation_model.py    # Layout model loading
│   ├── review_store.py        # Run storage, annotations, feedback
│   ├── logging_utils.py       # Logging configuration
│   ├── layouts.py             # Card layout definitions
│   └── schemas/               # JSON schemas for validation
│
├── templates/                 # Flask HTML templates
│   ├── index.html             # Upload page
│   └── review.html            # Review dashboard
│
├── static/                    # CSS/JS assets for web UI
├── logs/                      # Application logs
├── Outputs/                   # Saved processing runs (timestamped folders)
├── .venv/                     # Python virtual environment (auto-created)
└── .git/                      # Git repository
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.9+** (Python 3.13 recommended)
- **Homebrew** (macOS) — for installing system dependencies
- **Poppler** — PDF to image conversion (`brew install poppler`)
- **Tesseract** — Local OCR engine (`brew install tesseract`)
- **OpenAI API Key** (optional but recommended) — for remote OCR

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/LucasQuiles/PokeData.git
   cd PokeData
   ```

2. **Run the launcher (auto-installs dependencies):**
   ```bash
   ./pokedata
   ```

   The launcher script will:
   - Verify Python 3.9+ is installed
   - Create a virtual environment (`.venv/`)
   - Install Python packages from `requirements.txt`
   - Attempt to install Poppler and Tesseract via Homebrew if missing
   - Launch the Flask web app on `http://127.0.0.1:5000`
   - Open your default browser automatically

3. **Set OpenAI API Key (for remote OCR):**
   ```bash
   export OPENAI_API_KEY="your-api-key-here"
   ```

   Or add to your shell profile (`.bashrc`, `.zshrc`, etc.):
   ```bash
   echo 'export OPENAI_API_KEY="your-api-key-here"' >> ~/.zshrc
   source ~/.zshrc
   ```

---

## 📝 Usage

### Web Interface

1. **Start the server:**
   ```bash
   ./pokedata
   ```

2. **Upload a file:**
   - Navigate to `http://127.0.0.1:5000`
   - Drag & drop or select a PDF or image file (PNG, JPG, TIFF, BMP, WEBP)
   - Configure DPI (default: 300) and page limit (optional)
   - Click **Process**

3. **Download results:**
   - CSV file downloads automatically after processing
   - View past runs via the **Review** dashboard

4. **Review & annotate:**
   - Click **Review** in the navigation
   - Browse past processing runs
   - View low-confidence extractions
   - Add annotations or corrections

### Command-Line Interface

Process a PDF or image folder directly:

```bash
python pokedata.py --input path/to/cards.pdf --out results.csv --dpi 300
```

**Options:**
- `--input` — Path to PDF file or folder of images (required)
- `--out` — Output CSV file path (required)
- `--limit` — Limit number of pages/images processed (optional, default: all)
- `--dpi` — DPI for PDF conversion (optional, default: 300)

**Example:**
```bash
python pokedata.py --input scans/binder_page1.pdf --out catalog.csv --dpi 600 --limit 9
```

---

## 🛠️ Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | None | OpenAI API key for remote OCR (required for Vision API) |
| `POKEDATA_REMOTE_OCR` | `1` | Enable remote OCR (`1` = enabled, `0` = local-only) |
| `POKEDATA_REMOTE_CONFIDENCE_THRESHOLD` | `0.45` | Min confidence for remote OCR fields (0.0-1.0) |
| `POKEDATA_CONFIDENCE_THRESHOLD` | `0.9` | Min confidence for review dashboard flagging |
| `POKEDATA_AUTO_CROP` | `0` | Auto-crop card from background (`1` = enabled) |
| `POKEDATA_FRONT_ONLY` | `1` | Process only even-numbered pages (front faces only) |

### Launcher Options

```bash
./pokedata [OPTIONS]

Options:
  --port PORT       Run the web app on the given port (default: 5000)
  --no-browser      Skip opening the browser automatically
  -h, --help        Show help message
```

**Examples:**
```bash
# Run on custom port
./pokedata --port 8080

# Run without opening browser
./pokedata --no-browser

# Custom port + no browser
./pokedata --port 8080 --no-browser
```

---

## 📦 Dependencies

### System Dependencies

| Package | Purpose | Install Command |
|---------|---------|-----------------|
| **Poppler** | PDF to image conversion (`pdftoppm`) | `brew install poppler` |
| **Tesseract** | Local OCR engine | `brew install tesseract` |
| **Python 3.9+** | Runtime environment | `brew install python@3.13` |

### Python Dependencies

From `requirements.txt`:

```
Flask>=3.0              # Web framework
pytesseract             # Tesseract Python wrapper
Pillow                  # Image processing
pdf2image               # PDF to image conversion
opencv-python           # Advanced image processing (deskew, crop)
numpy                   # Numerical operations
openai>=2.1.0           # OpenAI API client (Vision API)
jsonschema>=4.22        # JSON schema validation
easyocr                 # Additional OCR engine (optional)
requests                # HTTP client
```

**Auto-install:** The `./pokedata` launcher automatically installs Python dependencies via `pip`.

---

## 🔄 Processing Workflow

### 1. Input → Image Preparation
- **PDF:** Converted to images via `pdf2image` (Poppler) at specified DPI
- **Images:** Loaded directly (PNG, JPG, TIFF, etc.)
- **Preprocessing:** Deskew, auto-crop (if enabled), grayscale conversion, contrast enhancement

### 2. Layout Detection
- Uses custom layout model to identify card type (Pokémon, Trainer, Energy)
- Crops specific regions (title, HP, bottom text, etc.)

### 3. OCR Extraction

**Remote OCR (Primary):**
- Sends image to OpenAI Vision API with structured JSON schema
- Extracts: name, HP, attacks, abilities, set code, card number, artist, etc.
- Returns confidence scores per field

**Local OCR (Fallback):**
- Tesseract OCR on full image and cropped regions
- Regex-based field extraction (HP, card number, artist, etc.)
- Layout-based extraction for specific regions

**Hybrid Approach:**
- Remote OCR provides structured data
- Local OCR fills gaps for low-confidence or missing fields
- Fallback suggestions stored in `notes` JSON field

### 4. Field Normalization
- Text normalization (unicode, punctuation)
- HP validation (numeric, 1-3 digits)
- Card number formatting (e.g., `12/102`)
- Set code validation (2-4 uppercase letters)
- Attack parsing (name, cost, damage, text)

### 5. Card Type Determination
- **Pokémon:** Has valid HP or attacks
- **Trainer:** No HP, no attacks, trainer keywords in text
- **Energy:** "Energy" in name, no HP
- **Unknown:** Insufficient data to classify

### 6. Output Generation
- **CSV:** One row per card with all extracted fields
- **JSON:** Structured JSON with full OCR response and confidence scores
- **Images:** Saved to `Outputs/[timestamp]/images/` for review
- **Logs:** Processing details in `logs/pokedata.log`

---

## 📊 Output Format

### CSV Columns

| Column | Description | Example |
|--------|-------------|---------|
| `source_image` | Path to processed image | `firstscan-pdf_page_001.png` |
| `page_index` | Page number (1-indexed) | `1` |
| `card_type` | Pokémon / Trainer / Energy / unknown | `pokemon` |
| `name` | Card name | `Charizard ex` |
| `hp` | Hit points (Pokémon only) | `180` |
| `evolves_from` | Evolution prerequisite | `Charmeleon` |
| `ability_name` | Ability name | `Burning Wings` |
| `ability_text` | Ability description | `Once during your turn...` |
| `attacks` | JSON array of attacks | `[{"name":"Fire Blast","cost":["Fire","Fire"],"damage":"120","text":""}]` |
| `set_name` | Set name | `Obsidian Flames` |
| `set_code` | Set code | `OBF` |
| `card_number` | Card number in set | `12/197` |
| `artist` | Illustrator name | `5ban Graphics` |
| `weakness` | Weakness type and multiplier | `Water ×2` |
| `resistance` | Resistance type and modifier | `Fighting -30` |
| `retreat` | Retreat cost (energy symbols) | `Colorless Colorless` |
| `notes` | JSON metadata (layout, warnings, suggestions) | `{"layout":"pokemon","cardType":"pokemon"}` |
| `rarity` | Rarity symbol/text | `Double Rare` |
| `quantity` | Count (default: 1) | `1` |
| `est_grade` | Estimated condition grade | `NM` |
| `page_sha1` | Image hash (duplicate detection) | `a3f2...` |
| `ocr_len` | OCR text length (chars) | `1234` |
| `parse_warnings` | Comma-separated warning codes | `artist_missing,hp_invalid_format` |

### JSON Structure (Structured Export)

```json
{
  "page_index": 1,
  "image": "path/to/image.png",
  "data": {
    "name": "Charizard ex",
    "hp": 180,
    "types": ["Fire"],
    "text": {
      "abilities": [{"name": "Burning Wings", "text": "..."}],
      "attacks": [{"name": "Fire Blast", "cost": ["Fire", "Fire"], "damage": "120"}]
    },
    "set": {"name": "Obsidian Flames", "code": "OBF"},
    "number": "12/197",
    "illustrator": "5ban Graphics",
    "_confidence": {
      "/name": 0.98,
      "/hp": 0.95,
      "/set/code": 0.87
    },
    "notes": {
      "unreadable": ["/rarity"],
      "lowConfidence": ["/set/code"]
    }
  }
}
```

---

## 🐛 Troubleshooting

### Common Issues

**1. Port 5000 already in use**
```bash
# Solution 1: Kill process on port 5000
lsof -ti tcp:5000 | xargs kill

# Solution 2: Use different port
./pokedata --port 8080
```

**2. Poppler not found (PDF processing fails)**
```
Error: Poppler utilities not detected
```
**Fix:**
```bash
brew install poppler
# Restart terminal
./pokedata
```

**3. Tesseract not found (OCR fails)**
```
⚠️  Tesseract not found
```
**Fix:**
```bash
brew install tesseract
# Restart terminal
./pokedata
```

**4. OpenAI API errors**
```
Error: OpenAI API key not set
```
**Fix:**
```bash
export OPENAI_API_KEY="sk-..."
./pokedata
```

**5. Virtual environment issues**
```
Failed to create virtualenv
```
**Fix:**
```bash
# Remove broken venv
rm -rf .venv
# Reinstall
./pokedata
```

**6. Permission denied on launcher**
```
bash: ./pokedata: Permission denied
```
**Fix:**
```bash
chmod +x pokedata
./pokedata
```

### Debug Mode

Enable detailed logging:
```bash
export FLASK_ENV=development
python -m flask --app app run --debug
```

View logs:
```bash
tail -f logs/pokedata.log
```

---

## 🔬 Advanced Features

### Custom Layout Models

Define custom bounding boxes for card regions:

Edit `pokedata_core/schemas/layout_model.json`:
```json
{
  "name": {"x": 0.1, "y": 0.05, "w": 0.8, "h": 0.08},
  "hp": {"x": 0.85, "y": 0.05, "w": 0.1, "h": 0.06}
}
```

### Grading Estimation

Automatic visual condition assessment based on:
- Edge wear detection
- Surface scratches
- Corner damage
- Centering

Grades: `Mint`, `NM` (Near Mint), `EX` (Excellent), `LP` (Lightly Played), `MP` (Moderately Played), `HP` (Heavily Played), `DMG` (Damaged)

### Batch Processing

Process entire collection folder:
```bash
for pdf in scans/*.pdf; do
    python pokedata.py --input "$pdf" --out "results/$(basename "$pdf" .pdf).csv"
done
```

### API Integration

Access processing runs via Flask API:

```bash
# List all runs
curl http://localhost:5000/api/runs

# Get run details
curl http://localhost:5000/api/runs/20251007-043026_firstscan-pdf

# Get low-confidence items
curl http://localhost:5000/api/runs/20251007-043026_firstscan-pdf/low-confidence?threshold=0.8

# Submit feedback
curl -X POST http://localhost:5000/api/runs/[run_id]/feedback \
  -H "Content-Type: application/json" \
  -d '{"page_index": 1, "image": "page_001.png", "field": "name", "action": "save", "value": "Corrected Name"}'
```

---

## 📋 Release Gates (for Developers)

Before pushing changes, verify:

1. **Launcher Syntax Integrity:**
   ```bash
   ./pokedata --help
   ```
   Should execute without errors.

2. **Dependency Self-Test:**
   ```bash
   ./pokedata --no-browser
   ```
   Should launch successfully, auto-installing missing dependencies.

3. **Regression Testing:**
   - Process a sample PDF and verify CSV output
   - Check web UI upload → download workflow
   - Verify review dashboard loads past runs

See [`AGENTS.md`](AGENTS.md) for full release gate protocols.

---

## 🤝 Contributing

### Development Setup

1. Fork and clone the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make changes and test locally: `./pokedata`
4. Run linting: `flake8 pokedata_core/ app.py pokedata.py`
5. Commit with descriptive messages
6. Push and open a pull request

### Code Standards

- **Python:** PEP 8 compliant, type hints where applicable
- **Bash:** ShellCheck compliant
- **Logging:** Use `pokedata_core.logging_utils.get_logger()`
- **Error Handling:** Graceful degradation, user-friendly messages

---

## 📜 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **Tesseract OCR** — Google's open-source OCR engine
- **Poppler** — PDF rendering library
- **OpenAI** — Vision API for structured OCR
- **Flask** — Lightweight web framework
- **Pillow / OpenCV** — Image processing libraries

---

## 📞 Support & Feedback

- **GitHub Issues:** https://github.com/LucasQuiles/PokeData/issues
- **Discussions:** https://github.com/LucasQuiles/PokeData/discussions

---

**Last Updated:** 2025-10-09
**Maintained by:** Lucas Quiles

---

## 🎯 Roadmap

### Completed ✅
- Hybrid OCR pipeline (local + remote)
- Web interface with upload/download
- CLI for batch processing
- Review dashboard with annotations
- Automatic grading estimation
- Layout detection for card types

### In Progress 🚧
- Mobile-responsive web UI
- Bulk export to collection management formats
- Training data collection from human feedback
- Performance optimizations for large PDFs

### Planned 📋
- Docker containerization
- Cloud deployment (AWS/GCP)
- Mobile app (iOS/Android)
- Integration with TCGPlayer / eBay APIs for pricing
- Multi-language support (Japanese, Korean TCG sets)
- Advanced grading with machine learning
- Real-time collaborative review sessions
