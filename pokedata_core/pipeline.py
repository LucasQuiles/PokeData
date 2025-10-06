"""Core OCR pipeline for extracting Pokémon TCG card details.

This module isolates the processing logic so it can be reused from both the CLI
script and the web application.
"""

from __future__ import annotations

import csv
import hashlib
import os
import re
import shutil
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Pattern, Tuple

import pytesseract
from PIL import Image, ImageFilter, ImageOps

from .annotation_model import load_layout_model
from .grading import estimate_grade
from .logging_utils import get_logger
from .remote_ocr import extract_card_fields

try:
    from pdf2image import convert_from_path  # requires Poppler installed on system

    _HAS_PDF2IMAGE = True
except Exception:  # pragma: no cover - best effort import
    _HAS_PDF2IMAGE = False

try:
    import cv2  # Optional; we gracefully degrade if missing

    _HAS_CV2 = True
except Exception:  # pragma: no cover - best effort import
    _HAS_CV2 = False

# Feature flags
USE_DESKEW = True
SAVE_DEBUG = False
MAX_OCR_CHARS = 10000

# Set code mapping placeholder. Add entries as you discover them.
SET_CODE_MAP: Dict[str, str] = {}


logger = get_logger("pipeline")
LAYOUT_MODEL = load_layout_model()
REMOTE_OCR_ENABLED = os.getenv("POKEDATA_REMOTE_OCR", "1") != "0"

# Regexes & heuristics
RE_HP = re.compile(r"\bHP\s*(\d{1,3})\b", re.IGNORECASE)
RE_EVOLVES = re.compile(r"\bEvolves\s+from\s+([A-Za-z0-9'\-. ]+)", re.IGNORECASE)
RE_ARTIST = re.compile(r"\bIllus\.\s*([A-Za-z0-9'\-.\s]+)", re.IGNORECASE)
RE_CARDNUM = re.compile(r"\b(\d{1,3}\s*/\s*\d{1,3})\b")
RE_SET_CODE = re.compile(r"\b([A-Z]{2,4})\s*(?=\d{1,3}\s*/\s*\d{1,3})")
RE_WEAKNESS = re.compile(r"\bweakness\b", re.IGNORECASE)
RE_RESIST = re.compile(r"\bresistance\b", re.IGNORECASE)
RE_RETREAT = re.compile(r"\bretreat\b", re.IGNORECASE)
RE_ABILITY_LINE = re.compile(r"\bAbility\b\s*([A-Za-z0-9'\- ]+)", re.IGNORECASE)
RE_ATTACK_LINE = re.compile(r"([A-Za-z][A-Za-z0-9'\- ]+?)\s+(\d{10,}|[1-9]\d{0,2}\+?)\b")


@dataclass
class CardRow:
    source_image: str
    page_index: int
    name: str = ""
    hp: str = ""
    evolves_from: str = ""
    ability_name: str = ""
    ability_text: str = ""
    attacks: str = ""
    set_name: str = ""
    set_code: str = ""
    card_number: str = ""
    artist: str = ""
    weakness: str = ""
    resistance: str = ""
    retreat: str = ""
    notes: str = ""
    rarity: str = ""
    quantity: str = "1"
    est_grade: str = ""
    page_sha1: str = ""
    ocr_len: int = 0
    parse_warnings: str = ""


@dataclass
class ProcessResult:
    rows: List[CardRow]
    images: List[Path]
    csv_path: Optional[Path] = None
    structured: List[Dict[str, str]] = field(default_factory=list)


def _pil_enhance(img: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(img)
    gray = ImageOps.autocontrast(gray)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
    return gray


def _cv2_deskew_if_available(pil_img: Image.Image) -> Image.Image:
    if not (USE_DESKEW and _HAS_CV2):
        return pil_img
    try:
        import numpy as np

        img = np.array(pil_img)
        if img.ndim == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img
        gray = cv2.bitwise_not(gray)
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        coords = cv2.findNonZero(thresh)
        if coords is None:
            return pil_img
        rect = cv2.minAreaRect(coords)
        angle = rect[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        (h, w) = img.shape[:2]
        M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
        rotated = cv2.warpAffine(
            img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )
        return Image.fromarray(rotated)
    except Exception:
        return pil_img


def _sha1_of_image(pil_img: Image.Image) -> str:
    h = hashlib.sha1()
    h.update(pil_img.tobytes())
    return h.hexdigest()


def _ocr(pil_img: Image.Image, lang: str = "eng") -> str:
    config = "--psm 6"
    try:
        text = pytesseract.image_to_string(pil_img, lang=lang, config=config)
        if len(text) > MAX_OCR_CHARS:
            text = text[:MAX_OCR_CHARS]
        return text
    except Exception:
        return ""


def _first_line_before(text: str, marker_regex: Pattern[str]) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    try:
        for i, ln in enumerate(lines):
            if marker_regex.search(ln):
                for j in range(i - 1, -1, -1):
                    cand = lines[j]
                    if 1 <= len(cand) <= 30 and re.search(r"[A-Za-z]", cand):
                        return cand
                break
    except Exception:
        pass
    for ln in lines[:4]:
        if 1 <= len(ln) <= 30 and re.search(r"[A-Za-z]", ln):
            return ln
    return ""


def _extract_block(
    text: str, start_idx: int, stop_patterns: List[Pattern[str]], max_chars: int = 400
) -> str:
    chunk = text[start_idx : start_idx + max_chars]
    stops = [m.start() for pat in stop_patterns for m in pat.finditer(chunk)]
    if stops:
        end = min(stops)
        return chunk[:end].strip()
    return chunk.strip()


def _grab_line_containing(text: str, pat: Pattern[str]) -> str:
    m = pat.search(text)
    if not m:
        return ""
    line_start = text.rfind("\n", 0, m.start()) + 1
    line_end = text.find("\n", m.end())
    if line_end == -1:
        line_end = len(text)
    return text[line_start:line_end].strip()


def parse_text_to_fields(raw_text: str) -> Tuple[Dict[str, str], List[str]]:
    warnings: List[str] = []
    out: Dict[str, str] = {}
    text = raw_text

    m = RE_HP.search(text)
    out["hp"] = m.group(1) if m else ""
    if not m:
        warnings.append("hp_missing")

    name = _first_line_before(text, RE_HP)
    out["name"] = name
    if not name:
        warnings.append("name_guess_failed")

    m = RE_EVOLVES.search(text)
    out["evolves_from"] = m.group(1).strip() if m else ""

    m = RE_ARTIST.search(text)
    out["artist"] = m.group(1).strip() if m else ""
    if not out["artist"]:
        warnings.append("artist_missing")

    mnum = RE_CARDNUM.search(text)
    out["card_number"] = mnum.group(1).replace(" ", "") if mnum else ""
    if not out["card_number"]:
        warnings.append("card_number_missing")
    mset = RE_SET_CODE.search(text) if mnum else None
    out["set_code"] = mset.group(1) if mset else ""
    out["set_name"] = SET_CODE_MAP.get(out["set_code"], "") if out["set_code"] else ""

    m = RE_ABILITY_LINE.search(text)
    if m:
        out["ability_name"] = m.group(1).strip()
        start = m.end()
        stop_pats = [RE_ATTACK_LINE, RE_WEAKNESS, RE_RESIST, RE_RETREAT, RE_CARDNUM]
        out["ability_text"] = _extract_block(text, start, stop_pats, max_chars=400)
    else:
        out["ability_name"] = ""
        out["ability_text"] = ""

    attacks: List[str] = []
    for mm in RE_ATTACK_LINE.finditer(text):
        aname = mm.group(1).strip()
        dmg = mm.group(2).strip()
        attacks.append(f"{aname} :: {dmg}")
    out["attacks"] = " | ".join(attacks)

    out["weakness"] = _grab_line_containing(text, RE_WEAKNESS)
    out["resistance"] = _grab_line_containing(text, RE_RESIST)
    out["retreat"] = _grab_line_containing(text, RE_RETREAT)

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    tail = lines[-8:]
    tail = [ln for ln in tail if not RE_CARDNUM.search(ln)]
    out["notes"] = " ".join(tail[-5:]) if tail else ""

    return out, warnings


def _postprocess_layout_field(label: str, text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    if label == "hp":
        m = RE_HP.search(cleaned)
        if m:
            return m.group(1)
        digits = re.findall(r"\d+", cleaned)
        return digits[0] if digits else cleaned
    if label == "card_number":
        m = RE_CARDNUM.search(cleaned)
        return m.group(1).replace(" ", "") if m else cleaned
    if label == "set_code":
        m = re.search(r"[A-Z]{2,4}", cleaned.upper())
        return m.group(0) if m else cleaned.upper()
    if label in {"name", "artist", "set_name"}:
        return cleaned.replace("\n", " ")
    return cleaned


def _extract_with_layout(pil: Image.Image) -> Dict[str, str]:
    if not LAYOUT_MODEL:
        return {}
    width, height = pil.size
    results: Dict[str, str] = {}
    for label, box in LAYOUT_MODEL.items():
        try:
            x = float(box.get("x", 0.0))
            y = float(box.get("y", 0.0))
            w = float(box.get("w", 0.0))
            h = float(box.get("h", 0.0))
            left = max(0.0, min(1.0, x)) * width
            top = max(0.0, min(1.0, y)) * height
            right = max(0.0, min(1.0, x + w)) * width
            bottom = max(0.0, min(1.0, y + h)) * height
            if right <= left or bottom <= top:
                continue
            crop = pil.crop((left, top, right, bottom))
            crop = _pil_enhance(crop)
            text = _ocr(crop, lang="eng")
            value = _postprocess_layout_field(label, text)
            if value:
                results[label] = value
        except Exception:
            logger.exception("Layout extraction failed for label %s", label)
    return results


def _compute_missing_warnings(fields: Dict[str, str]) -> List[str]:
    warnings: List[str] = []
    if not fields.get("hp"):
        warnings.append("hp_missing")
    if not fields.get("name"):
        warnings.append("name_guess_failed")
    if not fields.get("artist"):
        warnings.append("artist_missing")
    if not fields.get("card_number"):
        warnings.append("card_number_missing")
    return warnings


def _resolve_poppler_path() -> Path:
    candidates = [
        Path("/opt/homebrew/opt/poppler/bin"),
        Path("/usr/local/opt/poppler/bin"),
        Path("/usr/local/bin"),
        Path("/opt/homebrew/bin"),
    ]
    for candidate in candidates:
        if (candidate / "pdftoppm").exists():
            return candidate
    return Path()


def _ensure_poppler_available() -> None:
    if shutil.which("pdftoppm"):
        return

    auto_path = _resolve_poppler_path()
    if auto_path:
        current = os.environ.get("PATH", "")
        parts = current.split(os.pathsep) if current else []
        if str(auto_path) not in parts:
            os.environ["PATH"] = os.pathsep.join([str(auto_path)] + parts)
            logger.info("Added Poppler bin directory to PATH: %s", auto_path)
        if shutil.which("pdftoppm"):
            return

    raise RuntimeError(
        "Poppler utilities not detected. Install via `brew install poppler` or add pdftoppm to PATH."
    )


def pdf_to_images(pdf_path: Path, out_dir: Path, dpi: int = 300) -> List[Path]:
    if not _HAS_PDF2IMAGE:
        raise RuntimeError(
            "pdf2image not installed. `pip install pdf2image` and ensure Poppler is on PATH."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError

    _ensure_poppler_available()

    try:
        pages = convert_from_path(str(pdf_path), dpi=dpi)
    except PDFInfoNotInstalledError as exc:
        raise RuntimeError(
            "Poppler (pdftoppm/pdfinfo) is required for PDF processing. Install it and retry."
        ) from exc
    except PDFPageCountError as exc:
        raise RuntimeError(f"Failed to read PDF pages: {exc}") from exc
    except Exception as exc:  # pragma: no cover - unexpected pdf2image issue
        raise RuntimeError(f"Unexpected PDF conversion error: {exc}") from exc
    results: List[Path] = []
    for i, page in enumerate(pages, 1):
        p = out_dir / f"{pdf_path.stem}_page_{i:03d}.png"
        page.save(p, "PNG")
        results.append(p)
    logger.info("Converted %s into %d image(s) at %sdpi", pdf_path, len(results), dpi)
    return results


def collect_image_inputs(input_path: Path, dpi: int = 300) -> List[Path]:
    img_exts = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}
    if input_path.is_dir():
        return sorted([p for p in input_path.iterdir() if p.suffix.lower() in img_exts])
    if input_path.is_file():
        if input_path.suffix.lower() in img_exts:
            return [input_path]
        if input_path.suffix.lower() == ".pdf":
            return pdf_to_images(input_path, input_path.with_suffix(""), dpi=dpi)
        raise ValueError(f"Unsupported input type: {input_path.suffix}")
    raise FileNotFoundError(str(input_path))


def process_page(image_path: Path, index: int) -> Tuple[CardRow, Optional[Dict[str, str]]]:
    pil = Image.open(image_path).convert("RGB")
    pil = _cv2_deskew_if_available(pil)
    pil = _pil_enhance(pil)

    page_sha1 = _sha1_of_image(pil)
    fields: Dict[str, str] = {}
    structured_payload: Optional[Dict[str, str]] = None
    warnings: List[str] = []
    ocr_len = 0
    remote_used = False

    if REMOTE_OCR_ENABLED:
        try:
            fields = extract_card_fields(pil)
            structured_payload = fields.pop("_structured_raw", None)
            remote_used = True
            warnings = _compute_missing_warnings(fields)
            logger.info("Remote OCR succeeded for %s", image_path.name)
        except Exception as exc:
            remote_used = False
            warnings.append(f"remote_error:{exc}")
            logger.warning("Remote OCR failed for %s: %s", image_path.name, exc)

    if not remote_used:
        text = _ocr(pil, lang="eng")
        ocr_len = len(text)
        fields, warnings = parse_text_to_fields(text)
        layout_fields = _extract_with_layout(pil)
        if layout_fields:
            for key, value in layout_fields.items():
                if not value:
                    continue
                if key in fields:
                    if not fields[key]:
                        fields[key] = value
                else:
                    fields[key] = value
            if layout_fields.get("hp") and "hp_missing" in warnings:
                warnings.remove("hp_missing")
            if layout_fields.get("name") and "name_guess_failed" in warnings:
                warnings.remove("name_guess_failed")
            if layout_fields.get("artist") and "artist_missing" in warnings:
                warnings.remove("artist_missing")
            if layout_fields.get("card_number") and "card_number_missing" in warnings:
                warnings.remove("card_number_missing")
    else:
        # Remote response may still be missing critical fields; fill via heuristics when needed.
        missing_keys = [key for key in ("name", "hp", "card_number") if not fields.get(key)]
        if missing_keys:
            text = _ocr(pil, lang="eng")
            ocr_len = len(text)
            fallback_fields, fallback_warnings = parse_text_to_fields(text)
            for key in missing_keys:
                if fallback_fields.get(key):
                    fields[key] = fallback_fields[key]
            warnings = _compute_missing_warnings(fields)
            layout_fields = _extract_with_layout(pil)
            if layout_fields:
                for key, value in layout_fields.items():
                    if value and not fields.get(key):
                        fields[key] = value
                warnings = _compute_missing_warnings(fields)

    row = CardRow(
        source_image=str(image_path),
        page_index=index,
        page_sha1=page_sha1,
        ocr_len=ocr_len,
        parse_warnings=",".join(warnings),
        **fields,
    )
    grade = estimate_grade(image_path)
    if grade:
        row.est_grade = grade
    logger.debug(
        "Processed image %s (index=%s) length=%s chars warnings=%s",
        image_path,
        index,
        ocr_len,
        row.parse_warnings,
    )
    if structured_payload:
        structured_payload = {
            "page_index": index,
            "image": str(image_path),
            "data": structured_payload,
        }

    return row, structured_payload


def process_images(images: List[Path]) -> Tuple[List[CardRow], List[Dict[str, str]]]:
    rows: List[CardRow] = []
    structured_payloads: List[Dict[str, str]] = []
    for idx, img in enumerate(images, 1):
        try:
            row, structured = process_page(img, idx)
            rows.append(row)
            if structured:
                structured_payloads.append(structured)
        except Exception as exc:
            empty = CardRow(
                source_image=str(img),
                page_index=idx,
                parse_warnings=f"exception:{exc}",
            )
            rows.append(empty)
            logger.exception("Failed to process %s (index=%s)", img, idx)
    return rows, structured_payloads


def process_input_path(input_path: Path, limit: int = 0, dpi: int = 300) -> ProcessResult:
    if input_path.suffix.lower() == ".pdf":
        if not _HAS_PDF2IMAGE:
            raise RuntimeError(
                "pdf2image not installed (and Poppler needed). See README for setup."
            )
        images = pdf_to_images(input_path, input_path.with_suffix(""), dpi=dpi)
    else:
        images = collect_image_inputs(input_path, dpi=dpi)

    front_only = os.getenv("POKEDATA_FRONT_ONLY", "1") != "0"

    if front_only:
        filtered: List[Path] = []
        for idx, img in enumerate(images, 1):
            if idx % 2 == 0:
                filtered.append(img)
        if filtered:
            logger.info("Front-only mode: filtered %d → %d images", len(images), len(filtered))
            images = filtered

    if limit and limit > 0:
        images = images[:limit]

    logger.info(
        "Processing %d image(s) derived from %s (dpi=%s, limit=%s)",
        len(images),
        input_path,
        dpi,
        limit,
    )
    rows, structured = process_images(images)
    return ProcessResult(rows=rows, images=images, structured=structured)


def write_csv(rows: List[CardRow], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(CardRow(source_image="", page_index=0)).keys())
    with out_csv.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
    logger.info("Wrote CSV %s with %d row(s)", out_csv, len(rows))


def process_to_csv(
    input_path: Path, out_csv: Path, *, limit: int = 0, dpi: int = 300
) -> ProcessResult:
    result = process_input_path(input_path, limit=limit, dpi=dpi)
    write_csv(result.rows, out_csv)
    result.csv_path = out_csv
    return result


def ensure_dependencies_ready() -> None:
    if not _HAS_PDF2IMAGE:
        logger.warning(
            "pdf2image not available. PDF uploads will fail unless the dependency is installed."
        )
    try:
        _ensure_poppler_available()
    except RuntimeError as exc:
        logger.warning("%s", exc)
