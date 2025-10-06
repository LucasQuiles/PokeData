"""CLI entrypoint for the Pokémon card OCR pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path
import json

from pokedata_core.logging_utils import get_logger, setup_logging
from pokedata_core.pipeline import ensure_dependencies_ready, process_to_csv


def main() -> None:
    setup_logging()
    logger = get_logger("cli")
    ap = argparse.ArgumentParser(description="Pokémon TCG OCR → CSV")
    ap.add_argument("--input", required=True, help="PDF file or folder of images")
    ap.add_argument("--out", required=True, help="Output CSV path")
    ap.add_argument("--limit", type=int, default=0, help="Limit number of pages/images processed")
    ap.add_argument("--dpi", type=int, default=300, help="DPI for PDF to image conversion")
    args = ap.parse_args()

    ensure_dependencies_ready()

    input_path = Path(args.input)
    out_csv = Path(args.out)

    try:
        result = process_to_csv(input_path, out_csv, limit=args.limit, dpi=args.dpi)
        logger.info(
            "CLI run completed for %s -> %s (%d rows)",
            input_path,
            out_csv,
            len(result.rows),
        )
        print(f"Wrote {len(result.rows)} rows → {out_csv}")
        if result.structured:
            structured_path = out_csv.with_suffix(".json")
            structured_path.write_text(json.dumps(result.structured, indent=2), encoding="utf-8")
            logger.info("Structured JSON saved to %s", structured_path)
            print(f"Structured JSON saved to {structured_path}")
    except Exception as exc:
        logger.exception("CLI processing failed for %s", input_path)
        raise


if __name__ == "__main__":
    main()
