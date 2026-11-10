"""Findings the source already had, set aside by `--introduced`.

A document an edit starts from can already be broken: a comment an earlier
tool orphaned, a style nobody defined. `check` on the edited copy reports those
again, and a gate that fails on them blames the edit for damage it did not do.
An agent told to fix its output then goes looking for something it never
touched.

`introduced()` checks the source as well and sets aside each finding in the
edited file that the source already has. The same finding means:

- the same code, part and message. The message names the item (the comment id,
  the style name, the relationship id) but not where it sits. Positions move
  with every inserted paragraph, so `where` does not have to match.
- counted. A source with one orphaned comment absorbs one finding, so a second
  orphaned comment with the same message is still reported.
- matched at the same `where` first. When the edited copy has more of a finding
  than the source, the ones reported are those at a location the source does
  not have.

Some findings are never set aside, whatever the source has:

- fidelity findings (`FID`), which describe the edit itself;
- a check that did not complete (`INT001`) and an expectation (`EXP001`);
- every finding that says part of the file was not checked: an unreadable
  package or part, malformed XML, a comments part that cannot be resolved,
  Strict Open XML, text that could not be measured. Two files nobody could
  read are not "no new damage".

A source that cannot be read produces only findings of the last kind, so it
absorbs nothing, and the edited copy's findings are all reported.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Iterable, Sequence

from .archive import DEFAULT_ARCHIVE_LIMITS, ArchiveLimits
from .finding import Finding
from .inspector import check
from .pptx_checks import check_pptx

#: Findings that say part of a file was not checked.
UNCHECKED = frozenset({
    "PKG000", "PKG001", "PKG002", "PKG006", "PKG007", "PKG008", "PKG009",
    "XML001", "CMT006", "PPT000",
})

#: Never set aside, whatever the source has.
NEVER_INHERITED = UNCHECKED | {"INT001", "EXP001"}

#: The reason a set-aside finding carries in `--show-suppressed`, JSON and
#: SARIF.
REASON = "already in the source (--introduced)"

_DECK_SUFFIXES = (".pptx", ".potx", ".ppsx")


def inheritable(f: Finding) -> bool:
    """Whether a finding like this one in the source may absorb `f`."""
    return not f.code.startswith("FID") and f.code not in NEVER_INHERITED


def source_findings(source: str | Path, *,
                    limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS
                    ) -> list[Finding]:
    """What the self-check reports on the source, with the checker its type
    takes. A source that cannot be read returns only findings that absorb
    nothing."""
    path = Path(source)
    if path.suffix.lower() in _DECK_SUFFIXES:
        return check_pptx(path, limits=limits)
    return check(path, limits=limits)


def split(findings: Iterable[Finding], source: Sequence[Finding]
          ) -> tuple[list[Finding], list[tuple[Finding, str]]]:
    """(introduced, [(inherited, why)]), each in the order of `findings`."""
    findings = list(findings)
    exact = Counter(
        (f.code, f.part, f.message, f.where) for f in source if inheritable(f)
    )
    loose = Counter((f.code, f.part, f.message) for f in source if inheritable(f))

    inherited: set[int] = set()
    # Same location first, so the leftovers are the ones the source lacks.
    for i, f in enumerate(findings):
        if not inheritable(f):
            continue
        key = (f.code, f.part, f.message)
        if exact[key + (f.where,)] > 0 and loose[key] > 0:
            exact[key + (f.where,)] -= 1
            loose[key] -= 1
            inherited.add(i)
    for i, f in enumerate(findings):
        if i in inherited or not inheritable(f):
            continue
        key = (f.code, f.part, f.message)
        if loose[key] > 0:
            loose[key] -= 1
            inherited.add(i)

    kept = [f for i, f in enumerate(findings) if i not in inherited]
    aside = [(f, REASON) for i, f in enumerate(findings) if i in inherited]
    return kept, aside


def introduced(findings: Iterable[Finding], source: str | Path, *,
               limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS
               ) -> tuple[list[Finding], list[tuple[Finding, str]]]:
    """Separate the findings an edit introduced from those its source had.

    Returns (introduced, [(inherited, why)]). `findings` are the edited file's,
    usually `check(edited) + compare(source, edited)`. See the module
    docstring for what counts as the same finding and what is never set aside.

        >>> from ooxml_integrity import check, compare, introduced
        >>> found = check("edited.docx") + compare("original.docx", "edited.docx")
        >>> new, inherited = introduced(found, "original.docx")
    """
    return split(findings, source_findings(source, limits=limits))
