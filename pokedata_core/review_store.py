"""Utilities for persisting processed runs and annotation data."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .pipeline import ProcessResult
from .logging_utils import get_logger


RUNS_ROOT = Path(__file__).resolve().parent.parent / "Outputs"
logger = get_logger("review")


def _ensure_runs_root() -> Path:
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    return RUNS_ROOT


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "run"


def store_run(result: ProcessResult, source_name: str) -> Dict[str, Any]:
    root = _ensure_runs_root()
    now = datetime.utcnow()
    base = f"{now.strftime('%Y%m%d-%H%M%S')}_{_slugify(source_name)}"
    run_dir = root / base
    counter = 1
    while run_dir.exists():
        run_dir = root / f"{base}_{counter}"
        counter += 1

    images_dir = run_dir / "images"
    annotations_dir = run_dir / "annotations"
    images_dir.mkdir(parents=True, exist_ok=True)
    annotations_dir.mkdir(parents=True, exist_ok=True)

    pages: List[Dict[str, Any]] = []
    original_to_dest: Dict[str, str] = {}
    for idx, img_path in enumerate(result.images, 1):
        suffix = img_path.suffix.lower() or ".png"
        dest_name = f"page_{idx:03d}{suffix}"
        dest = images_dir / dest_name
        try:
            shutil.copy2(img_path, dest)
        except FileNotFoundError:
            continue
        original_to_dest[str(img_path)] = dest_name
        pages.append({"index": idx, "file": dest_name})

    csv_name = "cards.csv"
    csv_path = run_dir / csv_name
    if result.csv_path and result.csv_path.exists():
        shutil.copy2(result.csv_path, csv_path)
    else:
        csv_path.write_text("", encoding="utf-8")

    structured_payload = []
    if result.structured:
        for entry in result.structured:
            data = dict(entry)
            image_key = data.get("image")
            if image_key in original_to_dest:
                data["image"] = original_to_dest[image_key]
            structured_payload.append(data)
        structured_path = run_dir / "cards.json"
        structured_path.write_text(json.dumps(structured_payload, indent=2), encoding="utf-8")

    meta: Dict[str, Any] = {
        "run_id": run_dir.name,
        "source_name": source_name,
        "created_at": now.isoformat(timespec="seconds"),
        "csv": csv_name,
        "pages": pages,
        "rows": len(result.rows),
        "has_structured": bool(structured_payload),
    }

    with (run_dir / "run.json").open("w", encoding="utf-8") as fp:
        json.dump(meta, fp, indent=2)

    logger.info("Stored run %s with %d pages", meta["run_id"], len(pages))
    return meta


def read_structured(run_id: str) -> List[Dict[str, Any]]:
    run = load_run(run_id)
    cards_path = Path(run["run_dir"]) / "cards.json"
    if not cards_path.exists():
        return []
    try:
        with cards_path.open(encoding="utf-8") as fp:
            return json.load(fp)
    except json.JSONDecodeError:
        logger.warning("Malformed cards.json for run %s", run_id)
        return []


LOW_CONFIDENCE_FIELDS = [
    "name",
    "stage",
    "hp",
    "types",
    "number",
    "setboxLetters",
    "illustrator",
    "text.attacks",
    "text.weaknesses",
    "text.resistances",
    "text.retreatCost",
]


def low_confidence_entries(run_id: str, threshold: float = 0.9) -> List[Dict[str, Any]]:
    structured = read_structured(run_id)
    results: List[Dict[str, Any]] = []
    for entry in structured:
        data = entry.get("data") or entry.get("structured") or entry.get("card") or entry.get("data", {})
        if not isinstance(data, dict):
            data = entry.get("data", {})
        confidence_block = data.get("_confidence", {}) if isinstance(data.get("_confidence"), dict) else {}
        for field in LOW_CONFIDENCE_FIELDS:
            conf_value = _lookup_confidence(confidence_block, field)
            field_value = _lookup_field(data, field)
            if conf_value is None:
                if field_value in (None, "", []):
                    conf_value = 0.0
                else:
                    continue
            if conf_value < threshold:
                results.append(
                    {
                        "page_index": entry.get("page_index"),
                        "image": entry.get("image"),
                        "field": field,
                        "confidence": conf_value,
                        "value": field_value,
                        "data": data,
                    }
                )
    results.sort(key=lambda item: item.get("confidence", 0.0))
    return results


def _lookup_confidence(block: Dict[str, Any], field: str) -> Optional[float]:
    if not block:
        return None
    if field in block and isinstance(block[field], (int, float)):
        return float(block[field])
    # support nested e.g., text.attacks
    parts = field.split(".")
    if parts[0] in block and isinstance(block[parts[0]], (int, float)):
        return float(block[parts[0]])
    return None


def _lookup_field(data: Dict[str, Any], field: str) -> Any:
    parts = field.split(".")
    node = data
    for part in parts:
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node


def append_feedback(run_id: str, payload: Dict[str, Any]) -> Path:
    run = load_run(run_id)
    feedback_path = Path(run["run_dir"]) / "human_feedback.jsonl"
    with feedback_path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload))
        fp.write("\n")
    logger.info(
        "Recorded feedback for %s field %s (action=%s)",
        run_id,
        payload.get("field"),
        payload.get("action"),
    )
    return feedback_path


def list_runs() -> List[Dict[str, Any]]:
    root = _ensure_runs_root()
    runs: List[Dict[str, Any]] = []
    for path in sorted(root.iterdir(), reverse=True):
        if not path.is_dir():
            continue
        meta_path = path / "run.json"
        if not meta_path.exists():
            continue
        try:
            with meta_path.open(encoding="utf-8") as fp:
                meta = json.load(fp)
        except json.JSONDecodeError:
            continue
        meta["run_id"] = path.name
        runs.append(meta)
    return runs


def load_run(run_id: str) -> Dict[str, Any]:
    root = _ensure_runs_root()
    run_dir = root / run_id
    meta_path = run_dir / "run.json"
    if not meta_path.exists():
        raise FileNotFoundError(run_id)
    with meta_path.open(encoding="utf-8") as fp:
        meta = json.load(fp)
    meta["run_id"] = run_id
    meta["run_dir"] = str(run_dir)
    return meta


def get_image_path(run_id: str, image_name: str) -> Path:
    run = load_run(run_id)
    image_file = Path(image_name).name
    image_path = Path(run["run_dir"]) / "images" / image_file
    if not image_path.exists():
        raise FileNotFoundError(image_file)
    return image_path


def read_annotations(run_id: str, image_name: str) -> List[Dict[str, Any]]:
    run = load_run(run_id)
    annotations_dir = Path(run["run_dir"]) / "annotations"
    annotations_dir.mkdir(parents=True, exist_ok=True)
    file_path = annotations_dir / f"{Path(image_name).stem}.json"
    if not file_path.exists():
        return []
    with file_path.open(encoding="utf-8") as fp:
        return json.load(fp)


def write_annotations(run_id: str, image_name: str, annotations: List[Dict[str, Any]]) -> None:
    run = load_run(run_id)
    annotations_dir = Path(run["run_dir"]) / "annotations"
    annotations_dir.mkdir(parents=True, exist_ok=True)
    file_path = annotations_dir / f"{Path(image_name).stem}.json"
    with file_path.open("w", encoding="utf-8") as fp:
        json.dump(annotations, fp, indent=2)
    logger.info(
        "Saved %d annotation(s) for %s/%s", len(annotations), run_id, Path(image_name).name
    )
