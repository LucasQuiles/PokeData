"""Human-in-the-loop verification system for OCR accuracy testing.

This module enables interactive verification of OCR extractions, building
a ground truth dataset for accuracy measurement and prompt improvement.
"""

from __future__ import annotations

import json
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

from .logging_utils import get_logger


logger = get_logger("verification")


@dataclass
class VerificationResult:
    """Result of a single card verification."""
    image: str
    image_path: str
    image_sha1: str
    ocr_extraction: Dict[str, Any]
    verified_data: Dict[str, Any]
    corrections: Dict[str, Dict[str, Any]]
    status: str  # "approved" | "corrected" | "skipped"
    verified_by: str
    verified_at: str
    review_time_seconds: float
    notes: str = ""

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class VerificationSession:
    """Manages a card verification session."""

    def __init__(self, run_id: str, ocr_version: str = "v2.0", reviewer: str = "human"):
        """
        Initialize verification session.

        Args:
            run_id: Processing run ID (e.g., "20251007-052346_firstscan-pdf")
            ocr_version: OCR pipeline version being verified
            reviewer: Name/identifier of person verifying
        """
        self.run_id = run_id
        self.ocr_version = ocr_version
        self.reviewer = reviewer

        # File paths
        self.run_dir = Path("Outputs") / run_id
        self.ground_truth_file = self.run_dir / "ground_truth.jsonl"
        self.session_file = self.run_dir / "verification_session.json"
        self.resume_file = self.run_dir / "verification_resume.json"

        # Session state
        self.started_at = None
        self.completed_at = None
        self.verifications: List[VerificationResult] = []
        self.current_index = 0

        # Load existing session if resuming
        if self.resume_file.exists():
            self._load_resume_state()

        logger.info(
            "Initialized verification session: run_id=%s, ocr_version=%s, reviewer=%s",
            run_id, ocr_version, reviewer
        )

    def start(self):
        """Start new verification session."""
        self.started_at = datetime.now(timezone.utc).isoformat()
        logger.info("Started verification session at %s", self.started_at)

    def verify_card(
        self,
        card_data: Dict[str, Any],
        verified_data: Dict[str, Any],
        corrections: Dict[str, Dict],
        status: str,
        review_time: float,
        notes: str = "",
        image_path: Optional[Path] = None
    ) -> VerificationResult:
        """
        Record verification result for a card.

        Args:
            card_data: Original OCR extraction
            verified_data: Human-verified correct data
            corrections: Dict of corrected fields (field_name -> {ocr, correct, confidence})
            status: "approved" | "corrected" | "skipped"
            review_time: Time spent reviewing this card (seconds)
            notes: Optional notes from reviewer
            image_path: Path to card image

        Returns:
            VerificationResult object
        """
        # Calculate image SHA1 if path provided
        image_sha1 = ""
        if image_path and image_path.exists():
            image_sha1 = self._calculate_sha1(image_path)

        # Create verification result
        result = VerificationResult(
            image=str(image_path.name) if image_path else "",
            image_path=str(image_path) if image_path else "",
            image_sha1=image_sha1,
            ocr_extraction=card_data,
            verified_data=verified_data,
            corrections=corrections,
            status=status,
            verified_by=self.reviewer,
            verified_at=datetime.now(timezone.utc).isoformat(),
            review_time_seconds=review_time,
            notes=notes
        )

        # Store verification
        self.verifications.append(result)
        self.current_index += 1

        # Save to ground truth file
        self.save_ground_truth(result)

        # Save resume state
        self._save_resume_state()

        logger.info(
            "Verified card %d: %s (%s, %d corrections, %.1fs)",
            self.current_index,
            result.image,
            status,
            len(corrections),
            review_time
        )

        return result

    def save_ground_truth(self, verification: VerificationResult):
        """
        Append verified card to ground_truth.jsonl file.

        Args:
            verification: VerificationResult to save
        """
        # Ensure directory exists
        self.run_dir.mkdir(parents=True, exist_ok=True)

        # Append to JSONL file (one JSON object per line)
        with self.ground_truth_file.open("a", encoding="utf-8") as f:
            json_line = json.dumps(verification.to_dict(), ensure_ascii=False)
            f.write(json_line + "\n")

        logger.debug("Saved ground truth entry to %s", self.ground_truth_file)

    def calculate_accuracy(self) -> Dict[str, Any]:
        """
        Calculate accuracy metrics from verified cards.

        Returns:
            Dict with per-field and overall accuracy
        """
        if not self.verifications:
            return {"error": "No verified cards"}

        # Only include approved/corrected cards (not skipped)
        verified = [v for v in self.verifications if v.status != "skipped"]

        if not verified:
            return {"error": "No approved/corrected cards"}

        # Fields to track
        fields = ["name", "cardType", "hp", "stage", "evolvesFrom"]

        # Initialize counters
        accuracy = {}
        for field in fields:
            accuracy[field] = {
                "correct": 0,
                "total": 0,
                "accuracy": 0.0,
                "errors": []
            }

        # Count correct vs total for each field
        for v in verified:
            ocr = v.ocr_extraction
            verified_data = v.verified_data

            for field in fields:
                # Extract values (handle nested fields in notes JSON)
                ocr_val = self._extract_field(ocr, field)
                verified_val = self._extract_field(verified_data, field)

                # Normalize for comparison
                ocr_normalized = self._normalize_value(ocr_val)
                verified_normalized = self._normalize_value(verified_val)

                accuracy[field]["total"] += 1

                if ocr_normalized == verified_normalized:
                    accuracy[field]["correct"] += 1
                else:
                    accuracy[field]["errors"].append({
                        "image": v.image,
                        "ocr": ocr_val,
                        "correct": verified_val
                    })

        # Calculate accuracy percentages
        for field in fields:
            total = accuracy[field]["total"]
            correct = accuracy[field]["correct"]
            accuracy[field]["accuracy"] = correct / total if total > 0 else 0.0

        # Calculate overall accuracy
        total_fields = sum(a["total"] for a in accuracy.values())
        total_correct = sum(a["correct"] for a in accuracy.values())
        overall_accuracy = total_correct / total_fields if total_fields > 0 else 0.0

        return {
            "by_field": accuracy,
            "overall": {
                "correct": total_correct,
                "total": total_fields,
                "accuracy": overall_accuracy
            },
            "session": {
                "total_cards": len(self.verifications),
                "verified": len(verified),
                "skipped": len([v for v in self.verifications if v.status == "skipped"]),
                "corrections": len([v for v in verified if v.status == "corrected"])
            }
        }

    def generate_report(self) -> str:
        """
        Generate human-readable accuracy report.

        Returns:
            Markdown-formatted report string
        """
        accuracy = self.calculate_accuracy()

        if "error" in accuracy:
            return f"# Verification Report\n\nError: {accuracy['error']}"

        report = []
        report.append(f"# Verification Report: {self.run_id}\n")
        report.append(f"**OCR Version:** {self.ocr_version}")
        report.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d')}")
        report.append(f"**Reviewer:** {self.reviewer}")
        report.append(f"**Total Cards:** {accuracy['session']['total_cards']}")
        report.append(f"**Verified:** {accuracy['session']['verified']}")
        report.append(f"**Skipped:** {accuracy['session']['skipped']}")
        report.append(f"**Corrections:** {accuracy['session']['corrections']}\n")
        report.append("---\n")

        # Overall accuracy
        report.append("## Overall Accuracy\n")
        report.append("| Field | Correct | Total | Accuracy | Status |")
        report.append("|-------|---------|-------|----------|--------|")

        targets = {
            "name": 0.90,
            "cardType": 0.95,
            "hp": 0.95,
            "stage": 0.90,
            "evolvesFrom": 0.85
        }

        for field, stats in accuracy["by_field"].items():
            acc = stats["accuracy"]
            target = targets.get(field, 0.85)
            status = "✅" if acc >= target else ("⚠️" if acc >= target - 0.1 else "❌")

            report.append(
                f"| **{field}** | {stats['correct']}/{stats['total']} | "
                f"{stats['total']} | **{acc*100:.1f}%** {status} | {target*100:.0f}%+ |"
            )

        overall = accuracy["overall"]
        report.append(f"\n**Overall Accuracy:** {overall['accuracy']*100:.1f}% "
                      f"({overall['correct']}/{overall['total']} fields correct)\n")

        # Status summary
        pass_count = sum(1 for f, s in accuracy["by_field"].items() if s["accuracy"] >= targets.get(f, 0.85))
        total_fields = len(accuracy["by_field"])

        if pass_count == total_fields:
            report.append("**Status:** ✅ All fields meet targets\n")
        elif pass_count >= total_fields * 0.6:
            report.append(f"**Status:** ⚠️ {pass_count}/{total_fields} fields meet targets\n")
        else:
            report.append(f"**Status:** ❌ Only {pass_count}/{total_fields} fields meet targets\n")

        report.append("---\n")

        # Error details
        report.append("## Errors by Field\n")
        for field, stats in accuracy["by_field"].items():
            if stats["errors"]:
                report.append(f"\n### {field} ({len(stats['errors'])} errors)\n")
                for err in stats["errors"][:5]:  # Show first 5
                    report.append(f"- **{err['image']}:** OCR='{err['ocr']}' → Correct='{err['correct']}'")
                if len(stats["errors"]) > 5:
                    report.append(f"- _(and {len(stats['errors']) - 5} more)_")

        return "\n".join(report)

    def save_session(self):
        """Save session metadata to JSON file."""
        self.completed_at = datetime.now(timezone.utc).isoformat()

        accuracy = self.calculate_accuracy()

        session_data = {
            "run_id": self.run_id,
            "ocr_version": self.ocr_version,
            "reviewer": self.reviewer,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_cards": len(self.verifications),
            "verified_count": len([v for v in self.verifications if v.status != "skipped"]),
            "skipped_count": len([v for v in self.verifications if v.status == "skipped"]),
            "total_corrections": len([v for v in self.verifications if v.status == "corrected"]),
            "accuracy": accuracy
        }

        self.session_file.write_text(json.dumps(session_data, indent=2, ensure_ascii=False))
        logger.info("Saved session metadata to %s", self.session_file)

        # Generate and save report
        report = self.generate_report()
        report_file = self.run_dir / "verification_report.md"
        report_file.write_text(report)
        logger.info("Saved verification report to %s", report_file)

        # Clean up resume file
        if self.resume_file.exists():
            self.resume_file.unlink()

    def _save_resume_state(self):
        """Save current state for resume capability."""
        resume_data = {
            "run_id": self.run_id,
            "ocr_version": self.ocr_version,
            "reviewer": self.reviewer,
            "started_at": self.started_at,
            "current_index": self.current_index,
            "verified_count": len(self.verifications)
        }

        self.resume_file.write_text(json.dumps(resume_data, indent=2))

    def _load_resume_state(self):
        """Load previous session state for resume."""
        try:
            resume_data = json.loads(self.resume_file.read_text())
            self.started_at = resume_data.get("started_at")
            self.current_index = resume_data.get("current_index", 0)

            # Load existing verifications from ground_truth.jsonl
            if self.ground_truth_file.exists():
                with self.ground_truth_file.open("r") as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            # Reconstruct VerificationResult from dict
                            result = VerificationResult(**data)
                            self.verifications.append(result)

            logger.info(
                "Resumed session: %d cards already verified, resuming from index %d",
                len(self.verifications),
                self.current_index
            )

        except Exception as e:
            logger.warning("Failed to load resume state: %s", e)

    @staticmethod
    def _calculate_sha1(file_path: Path) -> str:
        """Calculate SHA1 hash of file."""
        sha1 = hashlib.sha1()
        with file_path.open("rb") as f:
            while chunk := f.read(8192):
                sha1.update(chunk)
        return sha1.hexdigest()

    @staticmethod
    def _extract_field(data: Dict, field: str) -> Any:
        """Extract field value from extraction dict (handles notes JSON)."""
        # Direct field
        if field in data:
            return data[field]

        # Check in notes JSON for Stage 1 extractions
        notes_str = data.get("notes", "{}")
        if isinstance(notes_str, str):
            try:
                notes = json.loads(notes_str)
                if field in notes:
                    return notes[field]
            except json.JSONDecodeError:
                pass

        return None

    @staticmethod
    def _normalize_value(value: Any) -> str:
        """Normalize value for comparison (lowercase, strip, handle None)."""
        if value is None or value == "":
            return ""
        if isinstance(value, (int, float)):
            return str(value)
        return str(value).strip().lower()
