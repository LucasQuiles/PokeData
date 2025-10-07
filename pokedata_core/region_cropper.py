"""Layout detection and region-specific OCR helpers."""

from __future__ import annotations

import re
import shlex
import string
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from PIL import Image, ImageOps
import pytesseract
from pytesseract import Output

from .layouts import POKEMON_LAYOUT, TRAINER_LAYOUT, Layout

__all__ = [
    "CroppedRegions",
    "detect_layout",
    "crop_regions",
    "extract_title_text",
    "extract_hp",
    "extract_bottom_text",
]


TRAINER_KEYWORDS = {"TRAINER", "SUPPORTER", "ITEM", "STADIUM"}
HEADER_WHITELIST = string.ascii_uppercase
TITLE_WHITELIST = string.ascii_letters + string.digits + "'-."
HP_WHITELIST = string.digits


@dataclass
class CroppedRegions:
    """Container for image crops keyed by semantic region name."""

    layout_id: str
    layout: Layout
    regions: Dict[str, Image.Image]


def detect_layout(image: Image.Image) -> str:
    width, height = image.size
    header_box = _normalize_to_box(image, (0.05, 0.02, 0.95, 0.14))
    header_img = image.crop(header_box)
    header_img = ImageOps.expand(header_img, border=5, fill="white")

    tokens = _extract_tokens(
        header_img,
        config=_build_tesseract_config(
            ["--psm", "6", "-c", f"tessedit_char_whitelist={HEADER_WHITELIST}"]
        ),
    )
    token_text = " ".join(token["text"] for token in tokens)

    text = pytesseract.image_to_string(
        header_img,
        config=_build_tesseract_config(
            ["--psm", "7", "-c", f"tessedit_char_whitelist={HEADER_WHITELIST}"]
        ),
    )
    combined = " ".join(part for part in (token_text, text) if part).strip()

    token_score = _score_trainer_tokens(tokens)
    color_score = _trainer_color_ratio(header_img)

    if _looks_like_trainer_banner(combined):
        return "trainer"
    if token_score >= 0.25:
        return "trainer"
    if token_score >= 0.12 and color_score >= 0.08:
        return "trainer"
    if color_score >= 0.22 and token_score >= 0.05:
        return "trainer"
    return "pokemon"


def crop_regions(image: Image.Image, layout_id: str) -> CroppedRegions:
    layout = TRAINER_LAYOUT if layout_id == "trainer" else POKEMON_LAYOUT
    crops: Dict[str, Image.Image] = {}
    for name, box in layout.regions.items():
        crops[name] = image.crop(_normalize_to_box(image, box))
    return CroppedRegions(layout_id=layout_id, layout=layout, regions=crops)


def extract_title_text(crops: CroppedRegions) -> str:
    title_img = crops.regions.get("title")
    if not title_img:
        return ""
    text = pytesseract.image_to_string(
        title_img,
        config=_build_tesseract_config(
            ["--psm", "7", "-c", f"tessedit_char_whitelist={TITLE_WHITELIST}"]
        ),
    ).strip()
    if crops.layout_id == "trainer":
        text = _strip_trainer_banner(text)
    return text


def extract_hp(crops: CroppedRegions) -> str:
    if crops.layout_id == "trainer":
        return ""
    hp_img = crops.regions.get("hp")
    if not hp_img:
        return ""
    text = pytesseract.image_to_string(
        hp_img,
        config=_build_tesseract_config(
            ["--psm", "7", "-c", f"tessedit_char_whitelist={HP_WHITELIST}"]
        ),
    ).strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits[:3]


def extract_bottom_text(crops: CroppedRegions) -> Tuple[str, str, str]:
    meta_img = crops.regions.get("bottom_meta")
    if not meta_img:
        return "", "", ""
    text = pytesseract.image_to_string(meta_img, config="--psm 6").strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    joined = " ".join(lines)
    card_number = _find_card_number(joined)
    artist = _find_artist(joined)
    setbox = _find_setbox(joined)
    return card_number, artist, setbox


def _normalize_to_box(image: Image.Image, box: Tuple[float, float, float, float]) -> Tuple[int, int, int, int]:
    width, height = image.size
    x0 = max(0, int(box[0] * width))
    y0 = max(0, int(box[1] * height))
    x1 = min(width, int(box[2] * width))
    y1 = min(height, int(box[3] * height))
    return x0, y0, x1, y1


def _strip_trainer_banner(text: str) -> str:
    if not text:
        return ""

    cleaned = text.strip()
    cleaned = re.sub(r"^[^A-Za-z]+", "", cleaned)
    cleaned = re.sub(
        r"^(TRAINER|SUPPORTER|ITEM|STADIUM)\b[:\-]*\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip(" :-")


def _looks_like_trainer_banner(text: str) -> bool:
    if not text:
        return False
    letters = re.sub(r"[^A-Z]", "", text.upper())
    return any(token in letters for token in TRAINER_KEYWORDS)


def _score_trainer_tokens(tokens: Sequence[Dict[str, object]]) -> float:
    if not tokens:
        return 0.0
    matches = 0.0
    total = 0.0
    for token in tokens:
        text = str(token.get("text", "")).strip()
        if not text:
            continue
        cleaned = re.sub(r"[^A-Z]", "", text.upper())
        if not cleaned:
            continue
        total += 1.0
        if any(keyword in cleaned for keyword in TRAINER_KEYWORDS):
            conf = float(token.get("confidence", 0.0) or 0.0)
            matches += 1.0 + max(conf, 0.0) / 100.0
    if total == 0:
        return 0.0
    return matches / total


def _trainer_color_ratio(image: Image.Image) -> float:
    if image is None:
        return 0.0
    hsv = image.convert("HSV")
    hsv_np = np.asarray(hsv)
    if hsv_np.size == 0:
        return 0.0
    hue = hsv_np[..., 0].astype(np.float32) * (360.0 / 255.0)
    sat = hsv_np[..., 1].astype(np.float32) / 255.0
    val = hsv_np[..., 2].astype(np.float32) / 255.0
    mask = (
        (hue >= 18.0)
        & (hue <= 48.0)
        & (sat >= 0.35)
        & (val >= 0.55)
    )
    if not mask.any():
        return 0.0
    return float(mask.sum()) / float(mask.size)


def _extract_tokens(image: Image.Image, config: str) -> List[Dict[str, object]]:
    try:
        data = pytesseract.image_to_data(
            image,
            output_type=Output.DICT,
            config=config,
        )
    except pytesseract.TesseractError:
        return []

    tokens: List[Dict[str, object]] = []
    n = len(data.get("text", []))
    for idx in range(n):
        text = str(data["text"][idx]).strip()
        if not text:
            continue
        try:
            conf_val = float(data.get("conf", [0])[idx])
        except (ValueError, TypeError, IndexError):
            conf_val = 0.0
        tokens.append(
            {
                "text": text,
                "confidence": conf_val,
                "bbox": (
                    int(data.get("left", [0])[idx]),
                    int(data.get("top", [0])[idx]),
                    int(data.get("width", [0])[idx]),
                    int(data.get("height", [0])[idx]),
                ),
            }
        )
    return tokens


def _find_card_number(text: str) -> str:
    import re

    match = re.search(r"(\w{1,3}\s*/\s*\w{1,3}|SWSH\d{3}|TG\d{2}|\d{3}/\d{3})", text, re.IGNORECASE)
    if match:
        return match.group(0).replace(" ", "")
    return ""


def _find_artist(text: str) -> str:
    import re

    match = re.search(r"illus\.?\s*([^|]+)$", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    tokens = text.split("©")
    if tokens and len(tokens[-1].strip()) < 40:
        return tokens[-1].strip()
    return ""


def _find_setbox(text: str) -> str:
    import re

    match = re.search(r"\b[A-Z]{2,4}\b", text)
    if match:
        return match.group(0)
    return ""


def _build_tesseract_config(args: Sequence[str]) -> str:
    """Return a shell-safe config string for pytesseract.

    pytesseract's ``config`` parameter is a string that is split with
    :func:`shlex.split` internally.  Any raw single quotes therefore start a
    quoted segment which raises ``ValueError('No closing quotation')`` unless
    they are escaped.  We expand single quotes using the standard POSIX
    ``'"'"'`` pattern so that the downstream splitter reconstructs the original
    argument verbatim.
    """

    escaped: list[str] = []
    for arg in args:
        if "'" in arg:
            escaped.append("'" + arg.replace("'", "'\"'\"'") + "'")
        else:
            escaped.append(shlex.quote(arg))
    return " ".join(escaped)
