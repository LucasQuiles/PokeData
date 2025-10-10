#!/usr/bin/env python3
"""
Phase 1 Testing Script: Compare v1.0 vs v2.0 OCR on sample cards.

This script enables testing the new Stage 1 extraction pipeline against
the original v1.0 pipeline to measure accuracy improvements.

Usage:
    # Test all cards from a previous processing run
    python test_phase1.py --run-id 20251007-052346_firstscan-pdf

    # Test specific image files
    python test_phase1.py --images path/to/card1.png path/to/card2.png

    # Test with detailed per-card output
    python test_phase1.py --run-id 20251007-052346_firstscan-pdf --detailed

    # Save results to JSON file
    python test_phase1.py --run-id 20251007-052346_firstscan-pdf --output results.json
"""

import argparse
import json
import sys
from pathlib import Path
from PIL import Image

from pokedata_core.ocr_comparison import compare_extraction, batch_compare, print_comparison_report
from pokedata_core.logging_utils import get_logger


logger = get_logger("test_phase1")


def test_single_card(image_path: str, verbose: bool = True):
    """
    Test a single card image.

    Args:
        image_path: Path to card image
        verbose: If True, print detailed output

    Returns:
        Tuple of (v1_results, v2_results, comparison)
    """
    logger.info("Testing single card: %s", image_path)

    try:
        pil_img = Image.open(image_path).convert("RGB")
    except Exception as e:
        logger.error("Failed to load image: %s", e)
        return None, None, None

    v1_results, v2_results, comparison = compare_extraction(pil_img)

    if not verbose:
        return v1_results, v2_results, comparison

    # Print results
    print("\n" + "="*80)
    print(f"Card: {Path(image_path).name}")
    print("="*80)

    print("\n--- v1.0 Results ---")
    print(f"Name:        {v1_results.get('name', 'N/A')}")
    print(f"Type:        {v1_results.get('card_type', 'N/A')}")
    print(f"HP:          {v1_results.get('hp', 'N/A')}")
    print(f"Set:         {v1_results.get('set_name', 'N/A')} ({v1_results.get('set_code', 'N/A')})")
    print(f"Card Number: {v1_results.get('card_number', 'N/A')}")
    print(f"Artist:      {v1_results.get('artist', 'N/A')}")
    print(f"Time:        {comparison['v1_time_seconds']:.2f}s")
    if comparison['v1_error']:
        print(f"ERROR:       {comparison['v1_error']}")

    print("\n--- v2.0 Results (Stage 1 Only) ---")
    print(f"Name:          {v2_results.get('name', 'N/A')}")
    print(f"Type:          {v2_results.get('card_type', 'N/A')}")
    print(f"HP:            {v2_results.get('hp', 'N/A')}")

    # Extract stage from notes JSON
    notes_str = v2_results.get('notes', '{}')
    try:
        notes = json.loads(notes_str)
        stage = notes.get('stage', 'N/A')
        confidence = notes.get('_confidence', {})
    except json.JSONDecodeError:
        stage = 'N/A'
        confidence = {}

    print(f"Stage:         {stage}")
    print(f"Evolves From:  {v2_results.get('evolves_from', 'N/A')}")
    print(f"Time:          {comparison['v2_time_seconds']:.2f}s")

    if confidence:
        print(f"\nConfidence Scores:")
        for field, score in confidence.items():
            print(f"  {field:15s}: {score:.2f}")

    if comparison['v2_error']:
        print(f"\nERROR: {comparison['v2_error']}")

    print("\n--- Field Comparison ---")
    for field, comp in comparison['field_comparison'].items():
        match_symbol = "✅" if comp['match'] else "❌"
        v1_val = comp['v1'] if comp['v1'] else "(empty)"
        v2_val = comp['v2'] if comp['v2'] else "(empty)"

        print(f"{match_symbol} {field:15s}: v1={v1_val!r:30s} | v2={v2_val!r}")

    print("\n--- Performance ---")
    delta = comparison['time_delta']
    if delta > 0:
        print(f"⚡ v2.0 is {delta:.2f}s FASTER ({comparison['summary']['speedup_factor']:.2f}x speedup)")
    else:
        print(f"v1.0 is {abs(delta):.2f}s faster")

    summary = comparison['summary']
    print(f"\nMatch Rate: {summary['match_rate']*100:.1f}% ({summary['matches']}/{summary['total_fields']} fields)")
    print(f"v2 Improvements: {summary['v2_improvements']} fields")
    print(f"v1 Advantages: {summary['v1_advantages']} fields")

    print("\n")

    return v1_results, v2_results, comparison


def test_run_directory(run_id: str, detailed: bool = False, output_file: str = None):
    """
    Test all cards from a previous processing run.

    Args:
        run_id: Run directory name (e.g., "20251007-052346_firstscan-pdf")
        detailed: If True, print detailed per-card results
        output_file: If provided, save results to JSON file
    """
    run_dir = Path("Outputs") / run_id
    image_dir = run_dir / "images"

    if not image_dir.exists():
        logger.error("Run directory not found: %s", image_dir)
        print(f"ERROR: Run directory not found: {image_dir}")
        print(f"\nAvailable runs:")
        outputs_dir = Path("Outputs")
        if outputs_dir.exists():
            runs = sorted([d.name for d in outputs_dir.iterdir() if d.is_dir() and not d.name.startswith(".")])
            for run in runs:
                print(f"  - {run}")
        return

    image_paths = sorted(image_dir.glob("page_*.png"))

    if not image_paths:
        logger.error("No images found in %s", image_dir)
        print(f"ERROR: No page_*.png images found in {image_dir}")
        return

    logger.info("Found %d images in %s", len(image_paths), run_id)
    print(f"\n🔍 Testing {len(image_paths)} cards from run: {run_id}")
    print(f"📂 Image directory: {image_dir}\n")

    # Run batch comparison
    results = batch_compare([str(p) for p in image_paths])

    # Print comparison report
    print_comparison_report(results, detailed=detailed)

    # Save detailed results if requested
    if output_file:
        output_path = Path(output_file)
        output_path.write_text(json.dumps(results, indent=2))
        logger.info("Detailed results saved to %s", output_path)
        print(f"💾 Detailed results saved to: {output_path}")
    else:
        # Save to default location in run directory
        default_output = run_dir / "phase1_comparison.json"
        default_output.write_text(json.dumps(results, indent=2))
        logger.info("Detailed results saved to %s", default_output)
        print(f"💾 Detailed results saved to: {default_output}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Phase 1 OCR Comparison Testing (v1.0 vs v2.0)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test all cards from a previous run
  python test_phase1.py --run-id 20251007-052346_firstscan-pdf

  # Test specific images
  python test_phase1.py --images card1.png card2.png

  # Test with detailed output and save to file
  python test_phase1.py --run-id 20251007-052346_firstscan-pdf --detailed --output results.json
        """
    )

    parser.add_argument(
        "--run-id",
        help="Test all cards from a previous run (e.g., 20251007-052346_firstscan-pdf)"
    )
    parser.add_argument(
        "--images",
        nargs="+",
        help="Test specific image files"
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Print detailed per-card comparison results"
    )
    parser.add_argument(
        "--output",
        help="Save detailed results to JSON file (default: Outputs/<run-id>/phase1_comparison.json)"
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.run_id and not args.images:
        parser.print_help()
        print("\nERROR: Must specify either --run-id or --images\n")
        sys.exit(1)

    # Run tests
    if args.run_id:
        test_run_directory(args.run_id, detailed=args.detailed, output_file=args.output)
    elif args.images:
        if len(args.images) == 1:
            # Single image - print detailed output
            test_single_card(args.images[0], verbose=True)
        else:
            # Multiple images - run batch comparison
            results = batch_compare(args.images)
            print_comparison_report(results, detailed=args.detailed)

            if args.output:
                Path(args.output).write_text(json.dumps(results, indent=2))
                print(f"\n💾 Results saved to: {args.output}")


if __name__ == "__main__":
    main()
