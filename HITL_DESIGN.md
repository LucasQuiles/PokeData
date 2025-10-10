# Human-in-the-Loop (HITL) Verification System Design

**Purpose:** Enable users to verify and correct OCR extractions during initial testing phase
**Goal:** Build ground truth dataset + measure real-world accuracy + identify failure patterns

---

## Overview

The HITL system presents each extracted card to the user for verification, allowing them to:
1. ✅ Approve correct extractions
2. ✏️ Correct wrong extractions
3. ⚠️ Flag problematic cards for later review
4. 📊 Track accuracy metrics in real-time

All corrections are stored and used to:
- Measure v1.0 vs v2.0 accuracy against ground truth
- Identify prompt improvement opportunities
- Build training dataset for future model fine-tuning

---

## User Flow

### Terminal Interface (Phase 1)

```
🔍 Card 1/10: page_002.png
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📸 Image: [Display card image in terminal if supported, or path]

🤖 OCR Extraction (v2.0):
   Name:          Stufful
   Card Type:     pokemon
   HP:            70
   Stage:         Basic
   Evolves From:  (empty)

   Confidence:    name=0.98, cardType=1.00, hp=0.95

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Options:
  [a] Approve (all correct)
  [c] Correct (one or more fields wrong)
  [s] Skip (review later)
  [v] View image (open in default viewer)
  [q] Quit and save progress

Your choice: _
```

#### If user selects "Correct":
```
Which field(s) need correction?
  [1] Name
  [2] Card Type
  [3] HP
  [4] Stage
  [5] Evolves From
  [a] All fields (start over)
  [b] Back to approve/skip

Enter number(s) separated by commas (e.g., 1,3): 5

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Correcting: Evolves From
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OCR said: (empty)

Enter correct value (or leave blank for none):

Saved: Evolves From = (empty) ✓

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Updated extraction:
   Name:          Stufful          ✓
   Card Type:     pokemon          ✓
   HP:            70               ✓
   Stage:         Basic            ✓
   Evolves From:  (empty)          ✓ CORRECTED

Approve this correction?
  [y] Yes, save and continue
  [n] No, correct again
  [s] Skip this card

Your choice: _
```

### Progress Tracking

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Session Progress: 3/10 cards reviewed (30%)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ Approved:    2 cards (20%)
✏️  Corrected:   1 card  (10%)
⏭️  Skipped:     0 cards (0%)
⏸️  Remaining:   7 cards (70%)

Accuracy so far:
  Name:        100% (3/3 correct)
  Card Type:   100% (3/3 correct)
  HP:          100% (3/3 correct)
  Stage:        67% (2/3 correct)  ⚠️
  Evolves From: 67% (2/3 correct)  ⚠️

Press Enter to continue...
```

---

## Data Storage

### Ground Truth Database

**File:** `Outputs/<run-id>/ground_truth.jsonl` (JSON Lines format)

Each line is a verified card:
```json
{
  "image": "page_002.png",
  "image_path": "Outputs/20251007-052346_firstscan-pdf/images/page_002.png",
  "image_sha1": "69adb794dcef0deaf519a8cb6dcbeaf3f8b8bd03",
  "ocr_extraction": {
    "name": "Stufful",
    "cardType": "pokemon",
    "hp": 70,
    "stage": "Basic",
    "evolvesFrom": null,
    "_confidence": {"name": 0.98, "cardType": 1.0, "hp": 0.95}
  },
  "verified_data": {
    "name": "Stufful",
    "cardType": "pokemon",
    "hp": 70,
    "stage": "Basic",
    "evolvesFrom": null
  },
  "corrections": {},
  "status": "approved",
  "verified_by": "human",
  "verified_at": "2025-10-09T20:30:15Z",
  "review_time_seconds": 8.3,
  "notes": "Easy card, all fields correct"
}
```

If corrections were made:
```json
{
  "image": "page_004.png",
  "ocr_extraction": {
    "name": "Lunatone",
    "cardType": "trainer",  // ❌ WRONG
    "hp": null,
    "stage": "Basic",      // ❌ WRONG (should be null for trainer)
    "evolvesFrom": null
  },
  "verified_data": {
    "name": "Lunatone",
    "cardType": "pokemon",  // ✓ CORRECTED
    "hp": 80,               // ✓ CORRECTED
    "stage": "Basic",       // ✓ VERIFIED
    "evolvesFrom": null
  },
  "corrections": {
    "cardType": {"ocr": "trainer", "correct": "pokemon", "confidence": 1.0},
    "hp": {"ocr": null, "correct": 80, "confidence": 1.0}
  },
  "status": "corrected",
  "verified_by": "human",
  "verified_at": "2025-10-09T20:31:42Z",
  "review_time_seconds": 25.7,
  "notes": "OCR misclassified as trainer, probably because HP wasn't detected"
}
```

### Session Metadata

**File:** `Outputs/<run-id>/verification_session.json`

```json
{
  "run_id": "20251007-052346_firstscan-pdf",
  "started_at": "2025-10-09T20:30:00Z",
  "completed_at": "2025-10-09T20:45:32Z",
  "total_cards": 10,
  "verified_count": 8,
  "skipped_count": 2,
  "total_corrections": 3,
  "accuracy_by_field": {
    "name": {"correct": 10, "total": 10, "accuracy": 1.0},
    "cardType": {"correct": 8, "total": 10, "accuracy": 0.8},
    "hp": {"correct": 9, "total": 10, "accuracy": 0.9},
    "stage": {"correct": 7, "total": 10, "accuracy": 0.7},
    "evolvesFrom": {"correct": 9, "total": 10, "accuracy": 0.9}
  },
  "ocr_version": "v2.0-stage1",
  "reviewer": "Lucas",
  "notes": "First test run of v2.0 pipeline"
}
```

---

## Implementation Architecture

### Files to Create

```
pokedata_core/
├── verification.py          # Core HITL logic
└── verification_ui.py       # Terminal UI rendering

Outputs/<run-id>/
├── ground_truth.jsonl       # Verified card data (one JSON per line)
├── verification_session.json # Session metadata
└── verification_resume.json # Resume state (if interrupted)

verify_cards.py              # Interactive CLI script
```

---

## Core Components

### 1. Verification Manager (`verification.py`)

```python
class VerificationSession:
    """Manages a card verification session."""

    def __init__(self, run_id: str, ocr_version: str = "v2.0"):
        self.run_id = run_id
        self.ocr_version = ocr_version
        self.ground_truth_file = Path(f"Outputs/{run_id}/ground_truth.jsonl")
        self.session_file = Path(f"Outputs/{run_id}/verification_session.json")
        self.resume_file = Path(f"Outputs/{run_id}/verification_resume.json")

    def verify_card(self, card_data: Dict, image_path: Path) -> Dict:
        """
        Present card to user for verification.

        Returns:
            {
                "status": "approved" | "corrected" | "skipped",
                "verified_data": {...},
                "corrections": {...},
                "review_time_seconds": 12.3,
                "notes": "..."
            }
        """

    def save_ground_truth(self, verification: Dict):
        """Append verified card to ground_truth.jsonl."""

    def calculate_accuracy(self) -> Dict:
        """Calculate accuracy from all verified cards."""

    def generate_report(self) -> str:
        """Generate human-readable accuracy report."""
```

### 2. Terminal UI (`verification_ui.py`)

```python
class VerificationUI:
    """Terminal-based verification interface."""

    def display_card(self, card_data: Dict, image_path: Path):
        """Render card extraction for review."""

    def prompt_approval(self) -> str:
        """Prompt: approve/correct/skip/view."""

    def prompt_corrections(self, fields: List[str]) -> Dict:
        """Interactive correction workflow."""

    def display_progress(self, session: VerificationSession):
        """Show session progress and accuracy stats."""

    def confirm_corrections(self, original: Dict, corrected: Dict) -> bool:
        """Show before/after comparison, confirm."""
```

### 3. Interactive Script (`verify_cards.py`)

```python
#!/usr/bin/env python3
"""
Interactive card verification script.

Usage:
    python verify_cards.py --run-id 20251007-052346_firstscan-pdf
    python verify_cards.py --run-id 20251007-052346_firstscan-pdf --resume
    python verify_cards.py --run-id 20251007-052346_firstscan-pdf --skip-approved
"""
```

---

## Features

### 1. Resume Support
If user quits mid-session, next run resumes from last card:
```
⏸️  Resuming previous session...
   Last verified: page_003.png (3/10 cards)
   Resuming from: page_004.png

Press Enter to continue...
```

### 2. Image Viewing
```
[v] View image

Opening page_002.png in default viewer...
(macOS: uses 'open', Linux: uses 'xdg-open', Windows: uses 'start')

Press Enter when ready to continue...
```

### 3. Batch Operations
```
[q] Quit and save progress

Save session progress?
  [y] Yes, save and quit (can resume later)
  [n] No, discard and quit
  [c] Cancel (continue verification)

Your choice: _
```

### 4. Accuracy Tracking
Real-time accuracy calculation:
- Per-field accuracy (name, cardType, hp, etc.)
- Overall accuracy (average across all fields)
- Confidence correlation (do low confidence scores = more errors?)

### 5. Notes/Comments
```
[Optional] Add notes about this card:
(Press Enter to skip)

> Card has foil/holo pattern making HP hard to read

Notes saved ✓
```

---

## Integration with Test Pipeline

### Modified `test_phase1.py`

Add `--verify` flag:
```bash
# Run test with human verification
python test_phase1.py --run-id 20251007-052346_firstscan-pdf --verify

# Resume verification session
python test_phase1.py --run-id 20251007-052346_firstscan-pdf --verify --resume

# Verify only low-confidence extractions
python test_phase1.py --run-id 20251007-052346_firstscan-pdf --verify --confidence-threshold 0.8
```

Workflow:
1. Run v2.0 extraction on all cards
2. For each card, prompt user for verification
3. Save verified data to `ground_truth.jsonl`
4. After all cards verified, generate accuracy report
5. Compare v1.0 vs v2.0 vs ground truth

---

## Accuracy Report Output

**File:** `Outputs/<run-id>/verification_report.md`

```markdown
# Verification Report: 20251007-052346_firstscan-pdf

**OCR Version:** v2.0-stage1
**Date:** 2025-10-09
**Reviewer:** Lucas
**Total Cards:** 10
**Verified:** 8 (80%)
**Skipped:** 2 (20%)

---

## Overall Accuracy

| Field | Correct | Total | Accuracy | Target |
|-------|---------|-------|----------|--------|
| **name** | 10/10 | 10 | **100%** ✅ | 90%+ |
| **cardType** | 8/10 | 10 | **80%** ⚠️ | 95%+ |
| **hp** | 9/10 | 10 | **90%** ✅ | 95%+ |
| **stage** | 7/10 | 10 | **70%** ❌ | 90%+ |
| **evolvesFrom** | 9/10 | 10 | **90%** ✅ | 85%+ |

**Overall Accuracy:** 86% (43/50 fields correct)

**Status:** ⚠️ Below target for cardType (80% vs 95%) and stage (70% vs 90%)

---

## Corrections Made

### Card 2: page_004.png (Lunatone)
- **cardType:** trainer → **pokemon** (confidence: 1.0)
- **hp:** (empty) → **80** (confidence: 1.0)
- **Notes:** OCR misclassified because HP wasn't detected

### Card 3: page_006.png (Centiskorch)
- **cardType:** trainer → **pokemon** (confidence: 1.0)
- **stage:** Stage 1 → **Stage 1** (no change, but confidence low)

### Card 7: page_014.png (Cinderace)
- **stage:** Stage 2 → **null** (confidence: 1.0)
- **Notes:** Card shows "VMAX" not "Stage 2"

---

## Error Patterns

### Pattern 1: Pokémon Misclassified as Trainer (3 occurrences)
**Cards:** page_004.png, page_006.png, page_012.png
**Root Cause:** OCR failed to detect HP, triggering "no HP = trainer" logic
**Fix:** Improve HP detection prompt, add layout-based fallback

### Pattern 2: Stage Detection Errors (3 occurrences)
**Cards:** page_006.png, page_010.png, page_014.png
**Root Cause:** Special mechanics (VMAX, VSTAR) not correctly mapped to stage
**Fix:** Update stage enum in schema, clarify prompt for special stages

---

## Confidence Score Analysis

| Confidence Range | Cards | Accuracy |
|------------------|-------|----------|
| 0.90 - 1.00 | 6 | 95% |
| 0.70 - 0.89 | 3 | 67% |
| 0.50 - 0.69 | 1 | 40% |
| < 0.50 | 0 | N/A |

**Finding:** Low confidence scores (< 0.9) correlate with errors.
**Recommendation:** Set review threshold at 0.85 to catch 80% of errors.

---

## Next Steps

1. ❌ **FAIL:** cardType accuracy (80%) below target (95%)
   - **Action:** Improve cardType classification prompt
   - **Test:** Re-run on same 10 cards after prompt update

2. ❌ **FAIL:** stage accuracy (70%) below target (90%)
   - **Action:** Add examples for VMAX/VSTAR/GX in prompt
   - **Test:** Add more special mechanic cards to test set

3. ✅ **PASS:** name accuracy (100%) exceeds target (90%)
   - **Action:** No changes needed

4. ✅ **PASS:** hp accuracy (90%) close to target (95%)
   - **Action:** Minor prompt tweaks, but acceptable

5. ✅ **PASS:** evolvesFrom accuracy (90%) exceeds target (85%)
   - **Action:** No changes needed

---

## Recommendations

### Immediate (Before Phase 2)
- Update cardType classification logic in prompt
- Add special stage examples (VMAX, VSTAR, GX, ex)
- Re-test on same 10 cards to validate improvements

### Short-term (Phase 2)
- Expand test set to 20 cards (include more edge cases)
- Add cards with foil/holo patterns (known difficulty)
- Test vintage cards (1999-2009 era)

### Long-term (Phase 3+)
- Build 100-card ground truth dataset
- Track improvements across prompt iterations
- Use verified data for model fine-tuning
```

---

## Success Metrics

### Phase 1 Verification Goals
- [ ] Verify at least 20 cards with v2.0
- [ ] Achieve 90%+ name accuracy
- [ ] Achieve 95%+ cardType accuracy
- [ ] Identify top 3 error patterns
- [ ] Generate actionable improvement recommendations

### Session Quality Metrics
- **Throughput:** 20-30 seconds per card average
- **Completion Rate:** 80%+ cards verified (not skipped)
- **Inter-rater Reliability:** Same card verified by 2 people = same result
- **Useful Notes:** 50%+ cards have notes explaining errors

---

## Future Enhancements

### Web-Based Interface (Phase 2)
Replace terminal UI with web interface:
- Side-by-side image + extraction display
- Click-to-edit fields
- Keyboard shortcuts (a=approve, c=correct, s=skip)
- Progress bar and accuracy dashboard
- Export to CSV/JSON

### Active Learning (Phase 3)
- Prioritize low-confidence cards for review
- Skip high-confidence cards (assume correct)
- Suggest corrections based on similar cards
- Track which cards take longest to verify (indicates ambiguity)

### Collaborative Verification (Phase 4)
- Multiple reviewers per card
- Flag disagreements for discussion
- Track reviewer accuracy (who's most reliable?)
- Consensus-based ground truth

---

**Next Steps:**
1. Implement `verification.py` and `verification_ui.py`
2. Create `verify_cards.py` interactive script
3. Test on 10-card sample
4. Measure accuracy and generate report
5. Iterate on prompt based on findings
