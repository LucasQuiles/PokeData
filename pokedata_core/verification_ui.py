"""Terminal-based UI for human-in-the-loop card verification.

This module provides an interactive terminal interface for reviewing
and correcting OCR extractions.
"""

from __future__ import annotations

import json
import sys
import subprocess
import platform
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from .logging_utils import get_logger


logger = get_logger("verification_ui")


class VerificationUI:
    """Terminal-based verification interface."""

    def __init__(self, color: bool = True):
        """
        Initialize UI.

        Args:
            color: Enable colored output (default: True)
        """
        self.color = color and sys.stdout.isatty()

    def display_card(self, card_data: Dict[str, Any], image_path: Path, card_num: int, total_cards: int):
        """
        Display card extraction for review.

        Args:
            card_data: OCR extraction data
            image_path: Path to card image
            card_num: Current card number (1-indexed)
            total_cards: Total number of cards
        """
        self._clear_screen()

        # Header
        self._print_header(f"Card {card_num}/{total_cards}: {image_path.name}")

        # Image info
        print(f"📸 Image: {image_path}")
        print(f"   Size: {self._get_file_size(image_path)}")
        print()

        # Extract data from card_data (handle Stage 1 format)
        name = card_data.get("name", "")
        card_type = card_data.get("cardType", card_data.get("card_type", ""))
        hp = card_data.get("hp", "")

        # Extract stage and evolvesFrom from notes if present
        notes_str = card_data.get("notes", "{}")
        stage = None
        evolves_from = card_data.get("evolvesFrom", card_data.get("evolves_from", ""))
        confidence = {}

        if isinstance(notes_str, str):
            try:
                notes = json.loads(notes_str)
                stage = notes.get("stage")
                confidence = notes.get("_confidence", {})
            except json.JSONDecodeError:
                pass

        # OCR Extraction display
        print(self._color("🤖 OCR Extraction (v2.0):", "cyan", bold=True))
        print(f"   Name:          {self._format_value(name)}")
        print(f"   Card Type:     {self._format_value(card_type)}")
        print(f"   HP:            {self._format_value(hp)}")
        print(f"   Stage:         {self._format_value(stage)}")
        print(f"   Evolves From:  {self._format_value(evolves_from)}")

        # Confidence scores
        if confidence:
            print()
            print(self._color("   Confidence:", "yellow"))
            for field, score in confidence.items():
                color = "green" if score >= 0.9 else ("yellow" if score >= 0.7 else "red")
                print(f"     {field:12s}: {self._color(f'{score:.2f}', color)}")

        print()

    def prompt_approval(self) -> str:
        """
        Prompt user for approval/correction/skip decision.

        Returns:
            Choice: 'a', 'c', 's', 'v', 'q'
        """
        self._print_separator("─")
        print("Options:")
        print("  [a] Approve (all correct)")
        print("  [c] Correct (one or more fields wrong)")
        print("  [s] Skip (review later)")
        print("  [v] View image (open in viewer)")
        print("  [q] Quit and save progress")
        print()

        while True:
            choice = input(self._color("Your choice: ", "cyan", bold=True)).strip().lower()
            if choice in ['a', 'c', 's', 'v', 'q']:
                return choice
            print(self._color("Invalid choice. Please enter a, c, s, v, or q.", "red"))

    def prompt_corrections(self, card_data: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Dict], str]:
        """
        Interactive correction workflow.

        Args:
            card_data: Original OCR extraction

        Returns:
            Tuple of (verified_data, corrections, notes)
        """
        # Extract current values
        name = card_data.get("name", "")
        card_type = card_data.get("cardType", card_data.get("card_type", ""))
        hp = card_data.get("hp", "")

        notes_str = card_data.get("notes", "{}")
        stage = None
        evolves_from = card_data.get("evolvesFrom", card_data.get("evolves_from", ""))
        confidence = {}

        if isinstance(notes_str, str):
            try:
                notes = json.loads(notes_str)
                stage = notes.get("stage")
                confidence = notes.get("_confidence", {})
            except json.JSONDecodeError:
                pass

        # Build field list
        fields = {
            "1": ("name", name),
            "2": ("cardType", card_type),
            "3": ("hp", hp),
            "4": ("stage", stage),
            "5": ("evolvesFrom", evolves_from)
        }

        # Prompt for which fields to correct
        self._clear_screen()
        self._print_header("Select Field(s) to Correct")

        print("Which field(s) need correction?")
        for num, (field_name, value) in fields.items():
            print(f"  [{num}] {field_name:12s}: {self._format_value(value)}")
        print("  [a] All fields (start over)")
        print("  [b] Back to approve/skip")
        print()

        while True:
            selection = input(self._color("Enter number(s) separated by commas (e.g., 1,3): ", "cyan")).strip()

            if selection.lower() == 'b':
                return None, None, None

            if selection.lower() == 'a':
                fields_to_correct = list(fields.keys())
                break

            try:
                fields_to_correct = [s.strip() for s in selection.split(",")]
                if all(f in fields for f in fields_to_correct):
                    break
                else:
                    print(self._color("Invalid selection. Please enter valid numbers.", "red"))
            except ValueError:
                print(self._color("Invalid input. Please enter numbers separated by commas.", "red"))

        # Correct each field
        verified_data = {
            "name": name,
            "cardType": card_type,
            "hp": hp,
            "stage": stage,
            "evolvesFrom": evolves_from
        }

        corrections = {}

        for field_num in fields_to_correct:
            field_name, current_value = fields[field_num]
            field_conf = confidence.get(field_name, 0.0)

            self._clear_screen()
            self._print_header(f"Correcting: {field_name}")

            print(f"OCR said: {self._format_value(current_value)}")
            print(f"Confidence: {field_conf:.2f}")
            print()

            # Get correct value
            new_value = self._prompt_field_value(field_name, current_value)

            # Store correction
            if new_value != current_value:
                verified_data[field_name] = new_value
                corrections[field_name] = {
                    "ocr": current_value,
                    "correct": new_value,
                    "confidence": field_conf
                }
                print(self._color(f"✓ Saved: {field_name} = {self._format_value(new_value)}", "green"))
            else:
                verified_data[field_name] = current_value
                print(self._color(f"✓ No change: {field_name} = {self._format_value(current_value)}", "yellow"))

            print()
            input(self._color("Press Enter to continue...", "cyan"))

        # Show updated extraction and confirm
        self._clear_screen()
        self._print_header("Review Corrections")

        print("Updated extraction:")
        for field_name in ["name", "cardType", "hp", "stage", "evolvesFrom"]:
            value = verified_data[field_name]
            if field_name in corrections:
                print(f"   {field_name:12s}: {self._format_value(value)} {self._color('✓ CORRECTED', 'green')}")
            else:
                print(f"   {field_name:12s}: {self._format_value(value)} ✓")

        print()
        print("Approve this correction?")
        print("  [y] Yes, save and continue")
        print("  [n] No, correct again")
        print("  [s] Skip this card")
        print()

        while True:
            choice = input(self._color("Your choice: ", "cyan")).strip().lower()
            if choice == 'y':
                # Prompt for notes
                print()
                notes = input(self._color("[Optional] Add notes about this card (press Enter to skip): ", "yellow")).strip()
                return verified_data, corrections, notes
            elif choice == 'n':
                return self.prompt_corrections(card_data)  # Recursive re-correction
            elif choice == 's':
                return None, None, None
            else:
                print(self._color("Invalid choice. Please enter y, n, or s.", "red"))

    def display_progress(self, verified_count: int, skipped_count: int, total_cards: int, accuracy: Optional[Dict] = None):
        """
        Display session progress.

        Args:
            verified_count: Number of cards verified
            skipped_count: Number of cards skipped
            total_cards: Total cards in session
            accuracy: Optional accuracy metrics
        """
        self._print_separator("━")
        print(f"Session Progress: {verified_count + skipped_count}/{total_cards} cards reviewed "
              f"({(verified_count + skipped_count) / total_cards * 100:.0f}%)")
        self._print_separator("━")

        print()
        print(f"✅ Verified:    {verified_count} cards ({verified_count / total_cards * 100:.0f}%)")
        print(f"⏭️  Skipped:     {skipped_count} cards ({skipped_count / total_cards * 100:.0f}%)")
        print(f"⏸️  Remaining:   {total_cards - verified_count - skipped_count} cards "
              f"({(total_cards - verified_count - skipped_count) / total_cards * 100:.0f}%)")

        if accuracy and "by_field" in accuracy:
            print()
            print("Accuracy so far:")
            for field, stats in accuracy["by_field"].items():
                acc = stats["accuracy"] * 100
                total = stats["total"]
                correct = stats["correct"]

                color = "green" if acc >= 90 else ("yellow" if acc >= 70 else "red")
                symbol = "✅" if acc >= 90 else ("⚠️" if acc >= 70 else "❌")

                print(f"  {field:15s}: {self._color(f'{acc:5.1f}%', color)} ({correct}/{total} correct) {symbol}")

        print()
        input(self._color("Press Enter to continue...", "cyan"))

    def view_image(self, image_path: Path):
        """
        Open image in default system viewer.

        Args:
            image_path: Path to image file
        """
        print(f"\nOpening {image_path.name} in default viewer...")

        try:
            system = platform.system()
            if system == "Darwin":  # macOS
                subprocess.run(["open", str(image_path)], check=True)
            elif system == "Linux":
                subprocess.run(["xdg-open", str(image_path)], check=True)
            elif system == "Windows":
                subprocess.run(["start", str(image_path)], shell=True, check=True)
            else:
                print(self._color(f"Cannot open image on {system}", "yellow"))
                return

            print(self._color("Image opened. Press Enter when ready to continue...", "cyan"))
            input()

        except subprocess.CalledProcessError as e:
            logger.warning("Failed to open image: %s", e)
            print(self._color(f"Failed to open image: {e}", "red"))
            input("Press Enter to continue...")

    def confirm_quit(self) -> str:
        """
        Confirm quit action.

        Returns:
            Choice: 'y', 'n', 'c'
        """
        print()
        print(self._color("Save session progress?", "yellow", bold=True))
        print("  [y] Yes, save and quit (can resume later)")
        print("  [n] No, discard and quit")
        print("  [c] Cancel (continue verification)")
        print()

        while True:
            choice = input(self._color("Your choice: ", "cyan")).strip().lower()
            if choice in ['y', 'n', 'c']:
                return choice
            print(self._color("Invalid choice. Please enter y, n, or c.", "red"))

    def display_resume_prompt(self, last_card: str, verified_count: int, total_cards: int) -> bool:
        """
        Display resume prompt for interrupted session.

        Args:
            last_card: Name of last verified card
            verified_count: Number of cards already verified
            total_cards: Total cards in session

        Returns:
            True to resume, False to start over
        """
        self._clear_screen()
        self._print_header("Resume Previous Session?")

        print(f"Found previous verification session:")
        print(f"  Last verified: {last_card}")
        print(f"  Progress: {verified_count}/{total_cards} cards ({verified_count / total_cards * 100:.0f}%)")
        print()
        print("Options:")
        print("  [r] Resume from where you left off")
        print("  [s] Start over (discard previous progress)")
        print()

        while True:
            choice = input(self._color("Your choice: ", "cyan")).strip().lower()
            if choice == 'r':
                return True
            elif choice == 's':
                return False
            else:
                print(self._color("Invalid choice. Please enter r or s.", "red"))

    def display_final_report(self, report: str):
        """
        Display final verification report.

        Args:
            report: Markdown-formatted report string
        """
        self._clear_screen()
        self._print_header("Verification Complete!")

        print(report)
        print()

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _prompt_field_value(self, field_name: str, current_value: Any) -> Any:
        """Prompt for corrected field value with type-specific validation."""
        if field_name == "cardType":
            return self._prompt_card_type()
        elif field_name == "hp":
            return self._prompt_hp()
        elif field_name == "stage":
            return self._prompt_stage()
        else:
            # Generic string input
            prompt = f"Enter correct value (or press Enter to keep '{current_value}'): "
            value = input(self._color(prompt, "cyan")).strip()
            return value if value else current_value

    def _prompt_card_type(self) -> str:
        """Prompt for card type with validation."""
        print("Card Type options:")
        print("  [1] pokemon")
        print("  [2] trainer")
        print("  [3] energy")
        print()

        while True:
            choice = input(self._color("Enter number: ", "cyan")).strip()
            if choice == '1':
                return "pokemon"
            elif choice == '2':
                return "trainer"
            elif choice == '3':
                return "energy"
            else:
                print(self._color("Invalid choice. Please enter 1, 2, or 3.", "red"))

    def _prompt_hp(self) -> Optional[int]:
        """Prompt for HP with validation."""
        while True:
            value = input(self._color("Enter HP (number or 'null' for none): ", "cyan")).strip()

            if value.lower() in ['null', 'none', '']:
                return None

            try:
                hp = int(value)
                if 10 <= hp <= 500:
                    return hp
                else:
                    print(self._color("HP must be between 10 and 500.", "red"))
            except ValueError:
                print(self._color("Invalid HP. Enter a number or 'null'.", "red"))

    def _prompt_stage(self) -> Optional[str]:
        """Prompt for stage with validation."""
        stages = ["Basic", "Stage 1", "Stage 2", "Mega Evolution", "BREAK", "VMAX", "VSTAR", "V", "GX", "EX", "ex"]

        print("Stage options (or press Enter for none):")
        for i, stage in enumerate(stages, 1):
            print(f"  [{i:2d}] {stage}")
        print()

        while True:
            choice = input(self._color("Enter number or stage name: ", "cyan")).strip()

            if not choice:
                return None

            # Try numeric choice
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(stages):
                    return stages[idx]
            except ValueError:
                pass

            # Try direct match
            if choice in stages:
                return choice

            print(self._color("Invalid choice. Enter a number, stage name, or press Enter for none.", "red"))

    def _format_value(self, value: Any) -> str:
        """Format value for display (handle None/empty)."""
        if value is None or value == "":
            return self._color("(empty)", "yellow")
        return str(value)

    def _get_file_size(self, file_path: Path) -> str:
        """Get human-readable file size."""
        try:
            size_bytes = file_path.stat().st_size
            for unit in ['B', 'KB', 'MB']:
                if size_bytes < 1024:
                    return f"{size_bytes:.1f} {unit}"
                size_bytes /= 1024
            return f"{size_bytes:.1f} GB"
        except Exception:
            return "unknown"

    def _clear_screen(self):
        """Clear terminal screen."""
        if platform.system() == "Windows":
            subprocess.call("cls", shell=True)
        else:
            subprocess.call("clear", shell=True)

    def _print_header(self, text: str):
        """Print formatted header."""
        self._print_separator("━")
        print(self._color(text, "cyan", bold=True))
        self._print_separator("━")
        print()

    def _print_separator(self, char: str = "─", width: int = 80):
        """Print separator line."""
        print(self._color(char * width, "blue"))

    def _color(self, text: str, color: str = "white", bold: bool = False) -> str:
        """
        Apply terminal color to text.

        Args:
            text: Text to color
            color: Color name (red, green, yellow, blue, cyan, white)
            bold: Apply bold formatting

        Returns:
            Colored text (or plain text if color disabled)
        """
        if not self.color:
            return text

        colors = {
            "red": "\033[91m",
            "green": "\033[92m",
            "yellow": "\033[93m",
            "blue": "\033[94m",
            "cyan": "\033[96m",
            "white": "\033[97m"
        }

        bold_code = "\033[1m" if bold else ""
        color_code = colors.get(color, colors["white"])
        reset = "\033[0m"

        return f"{bold_code}{color_code}{text}{reset}"
