"""Find the 3D character (.glb) shown on the dashboard instead of the status orb.

Search order:
1. an explicit path (`--model`), file or folder
2. the ROMEO_MODEL environment variable, file or folder
3. a `UI` folder in the current directory or in the Romeo checkout
   (e.g. D:\\Romeo\\UI when Romeo is installed from D:\\Romeo)
4. ~/.romeo/ui
In a folder, a file whose name mentions romeo/avatar/character wins;
otherwise the first .glb alphabetically.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional

from romeo.common.safety import romeo_home

PREFERRED = ("romeo", "avatar", "character")


def _checkout_root() -> Path:
    # src/romeo/ui/model.py -> checkout root (only meaningful for editable installs)
    return Path(__file__).resolve().parents[3]


def default_dirs() -> list[Path]:
    dirs = [Path.cwd() / "UI", _checkout_root() / "UI", romeo_home() / "ui"]
    unique: list[Path] = []
    for d in dirs:
        if d not in unique:
            unique.append(d)
    return unique


def pick_glb(folder: Path) -> Optional[Path]:
    if not folder.is_dir():
        return None
    files = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".glb"),
                   key=lambda p: p.name.lower())
    for p in files:
        if any(word in p.stem.lower() for word in PREFERRED):
            return p
    return files[0] if files else None


def _resolve(candidate: Path) -> Optional[Path]:
    if candidate.is_file():
        return candidate if candidate.suffix.lower() == ".glb" else None
    return pick_glb(candidate)


def find_model(explicit: Optional[str] = None, search: Optional[Iterable[Path]] = None) -> Optional[Path]:
    for raw in (explicit, os.environ.get("ROMEO_MODEL")):
        if raw:
            found = _resolve(Path(raw).expanduser())
            if found is None:
                raise FileNotFoundError(f"no .glb model at {raw}")
            return found.resolve()
    for folder in (search if search is not None else default_dirs()):
        found = pick_glb(folder)
        if found:
            return found.resolve()
    return None
