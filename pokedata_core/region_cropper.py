"""Layout detection and region cropping helpers."""

from __future__ import annotations

<<<<<<< ours
import io
=======
>>>>>>> theirs
import shlex
import string
from dataclasses import dataclass
from typing import Dict, Sequence, Tuple

import numpy as np
from PIL import Image, ImageOps
import pytesseract

from .layouts import POKEMON_LAYOUT, TRAINER_LAYOUT, Layout


TRAINER_KEYWORDS = {"TRAINER", "SUPPORTER", "ITEM", "STADIUM"}
TITLE_WHITELIST = string.ascii_letters + string.digits + "'-."
HP_WHITELIST = string.digits


@dataclass
class CroppedRegions:
    layout_id: str
    layout: Layout
    regions: Dict[str, Image.Image]


def detect_layout(image: Image.Image) -> str:
    width, height = image.size
    header_box = _normalize_to_box(image, (0.05, 0.02, 0.95, 0.14))
    header_img = image.crop(header_box)
    header_img = ImageOps.expand(header_img, border=5, fill="white")
    text = pytesseract.image_to_string(header_img, config="--psm 7").upper()
    for token in TRAINER_KEYWORDS:
        if token in text:
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
<<<<<<< ours
<<<<<<< ours
<<<<<<< ours
        config="--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789\'-.",
=======
        config="--psm 7 -c tessedit_char_whitelist=\"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'-.\"",
>>>>>>> theirs
=======
        config=_build_tesseract_config(
            ["--psm", "7", "-c", f"tessedit_char_whitelist={TITLE_WHITELIST}"]
        ),
>>>>>>> theirs
=======
        config=_build_tesseract_config(
            ["--psm", "7", "-c", f"tessedit_char_whitelist={TITLE_WHITELIST}"]
        ),
>>>>>>> theirs
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
    upper = text.upper()
    for token in TRAINER_KEYWORDS:
        if upper.startswith(token):
            idx = text.upper().find(token)
            text = text[idx + len(token) :]
    return text.strip(" :-")


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
<<<<<<< ours
    """Return a shell-safe config string for pytesseract."""

    return shlex.join(args)
=======
    """Return a shell-safe config string for pytesseract.

    pytesseract internally applies :func:`shlex.split` to the string we pass
    via ``config``.  The default quoting produced by :func:`shlex.join`
    serialises apostrophes by breaking the string into multiple segments such
    as ``'foo'"'"'bar`` which confuses the downstream splitter when it is
    handed back verbatim.  To keep the whitelist arguments stable we escape
    individual components manually, preferring double quotes when a value
    contains a single quote.
    """

    escaped: list[str] = []
    for arg in args:
        if "'" in arg and '"' not in arg:
            escaped.append(f'"{arg}"')
        else:
            escaped.append(shlex.quote(arg))
    return " ".join(escaped)
>>>>>>> theirs

