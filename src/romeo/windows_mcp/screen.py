"""Screenshots for the vision model (mss + Pillow), scaled with a coordinate grid."""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageDraw

MAX_EDGE = 1366  # keep images small enough for vision models


@dataclass
class Shot:
    png: bytes
    scale: float  # multiply image coords by this to get real screen coords
    width: int
    height: int


def _grab(monitor: int) -> Image.Image:
    import mss

    with mss.mss() as sct:
        mon = sct.monitors[monitor]
        raw = sct.grab(mon)
        return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")


def to_shot(img: Image.Image, grid: bool = True, max_edge: int = MAX_EDGE) -> Shot:
    scale = max(img.width, img.height) / max_edge if max(img.size) > max_edge else 1.0
    if scale != 1.0:
        img = img.resize((round(img.width / scale), round(img.height / scale)))
    if grid:
        draw = ImageDraw.Draw(img)
        step = 100
        for x in range(step, img.width, step):
            draw.line([(x, 0), (x, img.height)], fill=(255, 0, 0), width=1)
            draw.text((x + 2, 2), str(x), fill=(255, 0, 0))
        for y in range(step, img.height, step):
            draw.line([(0, y), (img.width, y)], fill=(255, 0, 0), width=1)
            draw.text((2, y + 2), str(y), fill=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return Shot(buf.getvalue(), scale, img.width, img.height)


def screenshot(monitor: int = 1, grid: bool = True) -> Shot:
    return to_shot(_grab(monitor), grid=grid)
