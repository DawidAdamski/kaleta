# SPDX-License-Identifier: AGPL-3.0-or-later
"""Load ``scripts/restyle_fidelity.py`` (a script, not a package) and draw test pictures."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest
from PIL import Image, ImageDraw

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "restyle_fidelity.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("restyle_fidelity", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["restyle_fidelity"] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def fidelity() -> ModuleType:
    return _load()


Box = tuple[int, int, int, int]


@pytest.fixture
def picture(tmp_path: Path) -> Callable[..., Path]:
    """``picture(name, size, black=[boxes])``: a white PNG with black rectangles."""

    def draw(name: str, size: tuple[int, int] = (400, 400), black: list[Box] | None = None) -> Path:
        image = Image.new("RGB", size, "white")
        pen = ImageDraw.Draw(image)
        for box in black or []:
            pen.rectangle((box[0], box[1], box[2] - 1, box[3] - 1), fill="black")
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
        return path

    return draw
