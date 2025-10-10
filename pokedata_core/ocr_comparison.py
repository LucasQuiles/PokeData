"""A/B testing wrapper for comparing v1.0 vs v2.0 OCR pipelines.

This module enables side-by-side comparison of extraction results,
performance metrics, and accuracy measurements.
"""

from __future__ import annotations

import time
from typing import Dict, List, Tuple
from PIL import Image

from . import remote_ocr  # v1.0
from . import remote_ocr_v2  # v2.0
from .logging_utils import get_logger


logger = get_logger("ocr_comparison")


def compare_extraction(pil_image: Image.Image) -> Tuple[Dict, Dict, Dict]:
    """
    Run both v1.0 and v2.0 extraction pipelines on the same image.

    Args:
        pil_image: PIL Image of card

    Returns:
        Tuple of (v1_results, v2_results, comparison_metrics)

    Example:
        >>> img = Image.open("card.png")
        >>> v1, v2, metrics = compare_extraction(img)
        >>> print(f"v2.0 is {metrics['time_delta']:.2f}s faster")
    """
    logger.info("Starting A/B comparison")

    # Run v1.0
    logger.debug("Running v1.0 pipeline...")
    start_v1 = time.time()
    try:
        v1_results = remote_ocr.extract_card_fields(pil_image)
        v1_error = None
    except Exception as e:
        logger.warning("v1.0 extraction failed: %s", e)
        v1_results = {}
        v1_error = str(e)
    v1_time = time.time() - start_v1

    # Run v2.0
    logger.debug("Running v2.0 pipeline...")
    start_v2 = time.time()
    try:
        v2_results = remote_ocr_v2.extract_card_fields_v2(pil_image)
        v2_error = None
    except Exception as e:
        logger.warning("v2.0 extraction failed: %s", e)
        v2_results = {}
        v2_error = str(e)
    v2_time = time.time() - start_v2

    # Compare results
    comparison = {
        "v1_time_seconds": v1_time,
        "v2_time_seconds": v2_time,
        "time_delta": v1_time - v2_time,  # Positive = v2 faster
        "v1_error": v1_error,
        "v2_error": v2_error,
        "field_comparison": _compare_fields(v1_results, v2_results),
        "summary": _generate_summary(v1_results, v2_results, v1_time, v2_time, v1_error, v2_error)
    }

    logger.info(
        "Comparison complete: v1=%.2fs, v2=%.2fs (delta: %+.2fs)",
        v1_time, v2_time, comparison["time_delta"]
    )

    return v1_results, v2_results, comparison


def _compare_fields(v1: Dict, v2: Dict) -> Dict[str, Dict]:
    """
    Compare field-by-field results.

    Args:
        v1: v1.0 extraction results
        v2: v2.0 extraction results

    Returns:
        Dict mapping field names to comparison details

    Example output:
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
            "v2_empty": not v2_val,
            "both_present": bool(v1_val and v2_val),
            "v1_only": bool(v1_val and not v2_val),
            "v2_only": bool(not v1_val and v2_val)
        }

    return comparison


def _generate_summary(v1: Dict, v2: Dict, v1_time: float, v2_time: float,
                      v1_error: str, v2_error: str) -> Dict:
    """Generate high-level comparison summary."""
    field_comp = _compare_fields(v1, v2)

    matches = sum(1 for fc in field_comp.values() if fc["match"])
    total_fields = len(field_comp)

    v2_improvements = sum(1 for fc in field_comp.values() if fc["v2_only"])
    v1_advantages = sum(1 for fc in field_comp.values() if fc["v1_only"])

    return {
        "match_rate": matches / total_fields if total_fields > 0 else 0.0,
        "matches": matches,
        "total_fields": total_fields,
        "v2_improvements": v2_improvements,  # Fields where v2 found value but v1 didn't
        "v1_advantages": v1_advantages,      # Fields where v1 found value but v2 didn't
        "v1_success": v1_error is None,
        "v2_success": v2_error is None,
        "v2_faster": v1_time > v2_time,
        "speedup_factor": v1_time / v2_time if v2_time > 0 else 0.0
    }


def batch_compare(image_paths: List[str]) -> Dict:
    """
    Run A/B comparison on multiple images.

    Args:
        image_paths: List of paths to card images

    Returns:
        Dict with batch statistics and detailed results

    Example:
        >>> paths = ["card1.png", "card2.png", "card3.png"]
        >>> results = batch_compare(paths)
        >>> print(f"v2.0 accuracy: {results['v2_name_accuracy']:.1%}")
    """
    logger.info("Starting batch comparison on %d images", len(image_paths))

    results = {
        "total_cards": len(image_paths),
        "v1_errors": 0,
        "v2_errors": 0,
        "v1_faster_count": 0,
        "v2_faster_count": 0,
        "total_v1_time": 0.0,
        "total_v2_time": 0.0,
        "field_match_counts": {},
        "detailed_results": []
    }

    for i, img_path in enumerate(image_paths, 1):
        logger.info("Processing %d/%d: %s", i, len(image_paths), img_path)

        try:
            pil_img = Image.open(img_path).convert("RGB")
        except Exception as e:
            logger.error("Failed to load image %s: %s", img_path, e)
            continue

        v1_res, v2_res, comp = compare_extraction(pil_img)

        # Track errors
        if comp["v1_error"]:
            results["v1_errors"] += 1
        if comp["v2_error"]:
            results["v2_errors"] += 1

        # Track speed
        results["total_v1_time"] += comp["v1_time_seconds"]
        results["total_v2_time"] += comp["v2_time_seconds"]

        if comp["time_delta"] > 0:
            results["v2_faster_count"] += 1
        else:
            results["v1_faster_count"] += 1

        # Track field matches
        for field, field_comp in comp["field_comparison"].items():
            if field not in results["field_match_counts"]:
                results["field_match_counts"][field] = {
                    "matches": 0,
                    "v1_empty": 0,
                    "v2_empty": 0,
                    "both_present": 0,
                    "total": 0
                }

            results["field_match_counts"][field]["total"] += 1
            if field_comp["match"]:
                results["field_match_counts"][field]["matches"] += 1
            if field_comp["v1_empty"]:
                results["field_match_counts"][field]["v1_empty"] += 1
            if field_comp["v2_empty"]:
                results["field_match_counts"][field]["v2_empty"] += 1
            if field_comp["both_present"]:
                results["field_match_counts"][field]["both_present"] += 1

        # Store detailed results
        results["detailed_results"].append({
            "image": str(img_path),
            "v1": v1_res,
            "v2": v2_res,
            "comparison": comp
        })

    # Calculate aggregated metrics
    results["avg_v1_time"] = results["total_v1_time"] / results["total_cards"] if results["total_cards"] > 0 else 0
    results["avg_v2_time"] = results["total_v2_time"] / results["total_cards"] if results["total_cards"] > 0 else 0
    results["avg_speedup"] = (results["total_v1_time"] - results["total_v2_time"]) / results["total_cards"] if results["total_cards"] > 0 else 0

    # Calculate field accuracy rates
    for field, counts in results["field_match_counts"].items():
        total = counts["total"]
        counts["match_rate"] = counts["matches"] / total if total > 0 else 0.0
        counts["v1_fill_rate"] = (total - counts["v1_empty"]) / total if total > 0 else 0.0
        counts["v2_fill_rate"] = (total - counts["v2_empty"]) / total if total > 0 else 0.0
        counts["both_present_rate"] = counts["both_present"] / total if total > 0 else 0.0

    logger.info("Batch comparison complete: %d cards processed", results["total_cards"])
    logger.info("v1.0 errors: %d, v2.0 errors: %d", results["v1_errors"], results["v2_errors"])
    logger.info("Avg speedup: %.2fs per card", results["avg_speedup"])

    return results


def print_comparison_report(comparison_results: Dict, detailed: bool = False):
    """
    Print human-readable comparison report.

    Args:
        comparison_results: Output from batch_compare()
        detailed: If True, print per-card details
    """
    print("\n" + "="*80)
    print("OCR PIPELINE COMPARISON REPORT (v1.0 vs v2.0)")
    print("="*80)

    print(f"\n📊 Overall Statistics:")
    print(f"  Total Cards Processed: {comparison_results['total_cards']}")
    print(f"  v1.0 Errors: {comparison_results['v1_errors']}")
    print(f"  v2.0 Errors: {comparison_results['v2_errors']}")

    print(f"\n⚡ Performance:")
    print(f"  v1.0 Avg Time: {comparison_results['avg_v1_time']:.2f}s per card")
    print(f"  v2.0 Avg Time: {comparison_results['avg_v2_time']:.2f}s per card")
    print(f"  Average Speedup: {comparison_results['avg_speedup']:.2f}s per card")
    print(f"  v2.0 Faster: {comparison_results['v2_faster_count']}/{comparison_results['total_cards']} cards")

    print(f"\n🎯 Field Accuracy:")
    for field, counts in sorted(comparison_results['field_match_counts'].items()):
        match_rate = counts['match_rate'] * 100
        v1_fill = counts['v1_fill_rate'] * 100
        v2_fill = counts['v2_fill_rate'] * 100

        print(f"  {field:15s}: Match={match_rate:5.1f}% | v1 Fill={v1_fill:5.1f}% | v2 Fill={v2_fill:5.1f}%")

    if detailed:
        print(f"\n📋 Detailed Per-Card Results:")
        for i, result in enumerate(comparison_results['detailed_results'], 1):
            print(f"\n  Card {i}: {result['image']}")
            comp = result['comparison']
            summary = comp['summary']

            print(f"    Match Rate: {summary['match_rate']*100:.1f}%")
            print(f"    Time: v1={comp['v1_time_seconds']:.2f}s, v2={comp['v2_time_seconds']:.2f}s")

            if comp['v1_error']:
                print(f"    v1 ERROR: {comp['v1_error']}")
            if comp['v2_error']:
                print(f"    v2 ERROR: {comp['v2_error']}")

            for field, fc in comp['field_comparison'].items():
                if not fc['match']:
                    print(f"      ❌ {field}: v1='{fc['v1']}' | v2='{fc['v2']}'")

    print("\n" + "="*80 + "\n")
