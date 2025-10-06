"""Derive and load layout models from human annotations."""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .logging_utils import get_logger


logger = get_logger("annotation")

OUTPUTS_DIR = Path(__file__).resolve().parent.parent / "Outputs"
MODEL_PATH = OUTPUTS_DIR / "layout_model.json"


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "Box":
        return cls(x=float(data["x"]), y=float(data["y"]), w=float(data["w"]), h=float(data["h"]))

    def to_dict(self) -> Dict[str, float]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}


def _collect_annotation_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    for run_dir in root.iterdir():
        ann_dir = run_dir / "annotations"
        if ann_dir.is_dir():
            yield from ann_dir.glob("*.json")


def build_layout_model(outputs_dir: Optional[Path] = None) -> Dict[str, Dict[str, float]]:
    root = outputs_dir or OUTPUTS_DIR
    boxes: Dict[str, List[Box]] = {}
    total_annotations = 0
    for ann_path in _collect_annotation_files(root):
        try:
            data = json.loads(ann_path.read_text())
        except json.JSONDecodeError:
            logger.warning("Skipping invalid annotation file %s", ann_path)
            continue
        for entry in data or []:
            label = entry.get("label")
            box = entry.get("box")
            if not label or not box:
                continue
            try:
                boxes.setdefault(label, []).append(Box.from_dict(box))
                total_annotations += 1
            except Exception:
                logger.exception("Failed to parse annotation %s", ann_path)
    if not boxes:
        logger.warning("No annotations found when building layout model")
        return {}

    model: Dict[str, Dict[str, float]] = {}
    for label, entries in boxes.items():
        xs = [b.x for b in entries]
        ys = [b.y for b in entries]
        ws = [b.w for b in entries]
        hs = [b.h for b in entries]
        model[label] = {
            "x": statistics.mean(xs),
            "y": statistics.mean(ys),
            "w": statistics.mean(ws),
            "h": statistics.mean(hs),
        }
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.write_text(json.dumps(model, indent=2))
    logger.info("Built layout model with %d labels (%d annotations)", len(model), total_annotations)
    return model


def load_layout_model(path: Optional[Path] = None) -> Dict[str, Dict[str, float]]:
    model_path = path or MODEL_PATH
    if not model_path.exists():
        return {}
    try:
        return json.loads(model_path.read_text())
    except json.JSONDecodeError:
        logger.warning("Layout model file %s is invalid", model_path)
        return {}


if __name__ == "__main__":  # pragma: no cover - simple CLI helper
    model = build_layout_model()
    print(json.dumps(model, indent=2))
