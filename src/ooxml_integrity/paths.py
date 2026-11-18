"""Document path handling shared by the checker and its commands."""
from __future__ import annotations

import os
from pathlib import Path

DECK_SUFFIXES = (".pptx", ".potx", ".ppsx")


def same_file(a: Path, b: Path) -> bool:
    """Whether `b` is `a`: the same path once resolved, or the same file
    through a symbolic or hard link, a case-insensitive name or a mount."""
    try:
        if a.resolve() == b.resolve():
            return True
        first, second = os.stat(a), os.stat(b)
    except (OSError, RuntimeError):
        return False
    return (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino)
