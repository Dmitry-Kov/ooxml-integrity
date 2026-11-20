"""Document path handling shared by the checker and its commands."""
from __future__ import annotations

import os
import stat
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


def check_report_destination(destination: Path, inputs: list[Path]) -> None:
    """Refuse run inputs, shared files and existing documents as report destinations."""
    for source in inputs:
        if same_file(source, destination):
            raise ValueError(f"{destination} points to input file {source}. "
                             "Choose a separate report path.")

    try:
        existing = destination.stat()
    except FileNotFoundError:
        return
    # Another name for the file may be a document outside this run.
    if existing.st_nlink > 1 and not stat.S_ISDIR(existing.st_mode):
        raise ValueError(f"{destination} has multiple hard links. Choose a separate report path.")

    # A shell-expanded glob can put the first document in the output argument.
    if stat.S_ISREG(existing.st_mode):
        suffixes = (".docx", *DECK_SUFFIXES)
        if destination.suffix.lower() in suffixes or destination.resolve().suffix.lower() in suffixes:
            raise ValueError(f"refusing to overwrite {destination}. "
                             "Put the input files first and use a separate report path.")
