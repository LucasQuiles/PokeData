"""Normalized layout definitions for Pokémon and Trainer-style cards."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class Layout:
    regions: Dict[str, tuple[float, float, float, float]]


POKEMON_LAYOUT = Layout(
    regions={
        "title": (0.05, 0.03, 0.95, 0.12),
        "hp": (0.78, 0.03, 0.95, 0.12),
        "type_line": (0.05, 0.12, 0.95, 0.18),
        "body": (0.05, 0.45, 0.95, 0.80),
        "bottom_mechanics": (0.05, 0.80, 0.95, 0.90),
        "bottom_meta": (0.05, 0.90, 0.95, 0.97),
        "weakness": (0.10, 0.81, 0.28, 0.89),
        "resistance": (0.30, 0.81, 0.48, 0.89),
        "retreat": (0.52, 0.81, 0.78, 0.89),
        "illustrator": (0.05, 0.91, 0.40, 0.96),
        "collector": (0.60, 0.91, 0.95, 0.96),
    }
)


TRAINER_LAYOUT = Layout(
    regions={
        "trainer_header": (0.05, 0.02, 0.95, 0.10),
        "title": (0.05, 0.10, 0.95, 0.20),
        "body": (0.05, 0.20, 0.95, 0.80),
        "bottom_meta": (0.05, 0.90, 0.95, 0.97),
        "illustrator": (0.05, 0.91, 0.40, 0.96),
        "collector": (0.60, 0.91, 0.95, 0.96),
    }
)

