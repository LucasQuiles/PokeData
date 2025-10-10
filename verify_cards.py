#!/usr/bin/env python3
"""
Interactive card verification script with human-in-the-loop feedback.

This script enables users to verify OCR extractions, building a ground truth
dataset for accuracy measurement and prompt improvement.

Usage:
    # Verify cards from a processing run
    python verify_cards.py --run-id 20251007-052346_firstscan-pdf

    # Resume interrupted session
    python verify_cards.py --run-id 20251007-052346_firstscan-pdf --resume

    # Verify only low-confidence extractions
    python verify_cards.py --run-id 20251007-052346_firstscan-pdf --confidence-threshold 0.8

    # Use v1.0 extractions instead of v2.0
    python verify_cards.py --run-id 20251007-052346_firstscan-pdf --ocr-version v1.0
"""

import argparse
import json
import sys
import time
from pathlib import Path
from PIL import Image

from pokedata_core.verification import VerificationSession
from pokedata_core.verification_ui import VerificationUI
from pokedata_core import remote_ocr_v2
from pokedata_core.logging_utils import get_logger


logger = get_logger("verify_cards")


def load_cards_from_run(run_id: str, confidence_threshold: Optional[float] = None) -> List[Tuple[Dict, Path]]:
    """
    Load cards from a processing run.

    Args:
        run_id: Run directory name
        confidence_threshold: If provided, only load cards below this confidence

    Returns:
        List of (card_data, image_path) tuples
    """
    run_dir = Path("Outputs") / run_id
    image_dir = run_dir / "images"

    if not image_dir.exists():
        raise FileNotFoundError(f"Run directory not found: {image_dir}")

    image_paths = sorted(image_dir.glob("page_*.png"))

    if not image_paths:
        raise FileNotFoundError(f"No images found in {image_dir}")

    logger.info("Found %d images in run %s", len(image_paths), run_id)

    # Extract cards using v2.0 (or load from existing results)
    cards = []

    for img_path in image_paths:
        # Try to load from existing results first
        card_data = None

        # Check if cards.json exists
        cards_json = run_dir / "cards.json"
        if cards_json.exists():
            try:
                all_cards = json.loads(cards_json.read_text())
                # Find card matching this image
                for card in all_cards:
                    if img_path.name in card.get("source_image", ""):
                        card_data = card
                        break
            except Exception as e:
                logger.warning("Failed to load from cards.json: %s", e)

        # If not found, run fresh extraction
        if not card_data:
            logger.info("Extracting %s...", img_path.name)
            try:
                pil_img = Image.open(img_path).convert("RGB")
                card_data = remote_ocr_v2.extract_card_fields_v2(pil_img)
                # Add image reference
                card_data["source_image"] = str(img_path)
            except Exception as e:
                logger.error("Failed to extract %s: %s", img_path.name, e)
                continue

        # Filter by confidence if threshold provided
        if confidence_threshold is not None:
            notes_str = card_data.get("notes", "{}")
            try:
                notes = json.loads(notes_str)
                confidence = notes.get("_confidence", {})

                # Calculate average confidence
                if confidence:
                    avg_conf = sum(confidence.values()) / len(confidence)
                    if avg_conf >= confidence_threshold:
                        logger.debug("Skipping %s (confidence %.2f >= threshold %.2f)",
                                     img_path.name, avg_conf, confidence_threshold)
                        continue
            except json.JSONDecodeError:
                pass

        cards.append((card_data, img_path))

    logger.info("Loaded %d cards for verification", len(cards))
    return cards


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Interactive card verification with human-in-the-loop feedback",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Verify all cards from a run
  python verify_cards.py --run-id 20251007-052346_firstscan-pdf

  # Resume interrupted session
  python verify_cards.py --run-id 20251007-052346_firstscan-pdf --resume

  # Verify only low-confidence cards
  python verify_cards.py --run-id 20251007-052346_firstscan-pdf --confidence-threshold 0.8

  # Specify reviewer name
  python verify_cards.py --run-id 20251007-052346_firstscan-pdf --reviewer "Lucas"
        """
    )

    parser.add_argument(
        "--run-id",
        required=True,
        help="Processing run ID (e.g., 20251007-052346_firstscan-pdf)"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume interrupted verification session"
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        help="Only verify cards with average confidence below this threshold (0.0-1.0)"
    )
    parser.add_argument(
        "--ocr-version",
        default="v2.0",
        help="OCR version being verified (default: v2.0)"
    )
    parser.add_argument(
        "--reviewer",
        default="human",
        help="Name/identifier of reviewer (default: human)"
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored terminal output"
    )

    args = parser.parse_args()

    # Initialize UI
    ui = VerificationUI(color=not args.no_color)

    # Initialize session
    session = VerificationSession(
        run_id=args.run_id,
        ocr_version=args.ocr_version,
        reviewer=args.reviewer
    )

    # Check for resume
    if args.resume and session.resume_file.exists():
        # Load existing verifications
        existing_count = len(session.verifications)

        if existing_count > 0:
            last_card = session.verifications[-1].image
            resume = ui.display_resume_prompt(last_card, existing_count, 0)

            if not resume:
                # Start over - clear resume file
                session.resume_file.unlink()
                session.verifications = []
                session.current_index = 0
    else:
        # Start new session
        session.start()

    # Load cards
    try:
        cards = load_cards_from_run(args.run_id, args.confidence_threshold)
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        print("\nAvailable runs:")
        outputs_dir = Path("Outputs")
        if outputs_dir.exists():
            runs = sorted([d.name for d in outputs_dir.iterdir() if d.is_dir() and not d.name.startswith(".")])
            for run in runs:
                print(f"  - {run}")
        sys.exit(1)

    if not cards:
        print("❌ No cards to verify (all cards above confidence threshold or no cards found)")
        sys.exit(1)

    # Skip already-verified cards
    cards_to_verify = cards[session.current_index:]

    print(f"\n🔍 Starting verification session")
    print(f"   Run ID: {args.run_id}")
    print(f"   Total cards: {len(cards)}")
    print(f"   Already verified: {session.current_index}")
    print(f"   Remaining: {len(cards_to_verify)}")
    print()
    input("Press Enter to begin...")

    # Verification loop
    for i, (card_data, image_path) in enumerate(cards_to_verify, start=session.current_index + 1):
        start_time = time.time()

        # Display card
        ui.display_card(card_data, image_path, i, len(cards))

        # Prompt for action
        while True:
            choice = ui.prompt_approval()

            if choice == 'a':
                # Approve
                verified_data = {
                    "name": card_data.get("name", ""),
                    "cardType": card_data.get("cardType", card_data.get("card_type", "")),
                    "hp": card_data.get("hp", ""),
                    "stage": None,
                    "evolvesFrom": card_data.get("evolvesFrom", card_data.get("evolves_from", ""))
                }

                # Extract stage from notes
                notes_str = card_data.get("notes", "{}")
                if isinstance(notes_str, str):
                    try:
                        notes = json.loads(notes_str)
                        verified_data["stage"] = notes.get("stage")
                    except json.JSONDecodeError:
                        pass

                review_time = time.time() - start_time

                session.verify_card(
                    card_data=card_data,
                    verified_data=verified_data,
                    corrections={},
                    status="approved",
                    review_time=review_time,
                    image_path=image_path
                )
                break

            elif choice == 'c':
                # Correct
                result = ui.prompt_corrections(card_data)

                if result[0] is None:
                    # User cancelled - go back to prompt
                    continue

                verified_data, corrections, notes = result
                review_time = time.time() - start_time

                session.verify_card(
                    card_data=card_data,
                    verified_data=verified_data,
                    corrections=corrections,
                    status="corrected",
                    review_time=review_time,
                    notes=notes,
                    image_path=image_path
                )
                break

            elif choice == 's':
                # Skip
                review_time = time.time() - start_time

                session.verify_card(
                    card_data=card_data,
                    verified_data={},
                    corrections={},
                    status="skipped",
                    review_time=review_time,
                    notes="Skipped for later review",
                    image_path=image_path
                )
                break

            elif choice == 'v':
                # View image
                ui.view_image(image_path)
                ui.display_card(card_data, image_path, i, len(cards))

            elif choice == 'q':
                # Quit
                quit_choice = ui.confirm_quit()

                if quit_choice == 'y':
                    # Save and quit
                    session.save_session()
                    print("\n✅ Session saved. You can resume later with --resume flag.")
                    sys.exit(0)
                elif quit_choice == 'n':
                    # Discard and quit
                    print("\n⚠️  Discarding session progress.")
                    sys.exit(0)
                elif quit_choice == 'c':
                    # Continue
                    ui.display_card(card_data, image_path, i, len(cards))

        # Show progress periodically
        if i % 5 == 0 or i == len(cards):
            verified_count = len([v for v in session.verifications if v.status != "skipped"])
            skipped_count = len([v for v in session.verifications if v.status == "skipped"])
            accuracy = session.calculate_accuracy()

            ui.display_progress(verified_count, skipped_count, len(cards), accuracy)

    # Session complete
    session.save_session()

    # Display final report
    report = session.generate_report()
    ui.display_final_report(report)

    print(f"\n✅ Verification complete!")
    print(f"   Ground truth: {session.ground_truth_file}")
    print(f"   Session data: {session.session_file}")
    print(f"   Report: {session.run_dir / 'verification_report.md'}")
    print()


if __name__ == "__main__":
    main()
