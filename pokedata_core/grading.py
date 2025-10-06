"""Estimate card grade from PSA slab images using EasyOCR."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import numpy as np

try:
    import cv2  # type: ignore
    import easyocr  # type: ignore
    import requests  # type: ignore

    _HAS_EASYOCR = True
    _READER = None
except Exception:  # pragma: no cover - optional dependency
    _HAS_EASYOCR = False
    _READER = None


def _get_reader():
    global _READER
    if _READER is None:
        _READER = easyocr.Reader(["en"])
    return _READER


def estimate_grade(image_path: Path, *, debug_dir: Optional[Path] = None, scale: float = 0.5) -> Optional[str]:
    if not _HAS_EASYOCR:
        return None

    path = str(image_path)
    if path.startswith(("http://", "https://")):
        try:
            response = requests.get(path, timeout=10)
            response.raise_for_status()
            data = np.frombuffer(response.content, np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        except Exception:
            img = None
    else:
        img = cv2.imread(path)

    if img is None:
        return None

    img = cv2.resize(img, (int(img.shape[1] * scale), int(img.shape[0] * scale)), interpolation=cv2.INTER_AREA)
    h, _ = img.shape[:2]

    top_crop = img[: int(h * 0.3), :]
    gray = cv2.cvtColor(top_crop, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    contours = [cv2.boundingRect(cnt) for cnt in contours]
    contours.sort(key=lambda r: r[2] * r[3], reverse=True)

    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)

    reader = _get_reader()

    for idx, (x, y, w_rect, h_rect) in enumerate(contours):
        if w_rect * h_rect < 500 or w_rect < 20 or h_rect < 10:
            continue
        aspect_ratio = w_rect / h_rect
        if aspect_ratio < 2.5 or aspect_ratio > 5:
            continue

        grade_crop = gray[y : y + h_rect, x : x + w_rect]
        if debug_dir:
            cv2.imwrite(str(debug_dir / f"crop_{idx}.png"), grade_crop)

        h_crop, w_crop = grade_crop.shape
        focused_crop = grade_crop[int(h_crop * 0.3) :, int(w_crop * 0.7) :]

        try:
            result = reader.readtext(focused_crop)
        except Exception:
            continue

        for _, text, _ in result:
            text_upper = text.upper()
            if "GEM MT" in text_upper or "GEM" in text_upper:
                return "10"
            if "MINT" in text_upper:
                return "9"

    return None
