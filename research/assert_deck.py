"""Assert the reference deck still reports exactly the defects it was built with.

Why this exists rather than a bare `docx-integrity check corpus/deck.pptx`:
the exit code alone is a bad assertion for CI. If the runner has no usable
fonts, every paragraph is skipped, PPT001 degrades from error to warning, and
the command exits 0 - so a check that only looks at the exit code passes an
environment where the tool measured nothing. That is the exact failure mode
the tool is supposed to catch in other people's pipelines, so it must not be
able to hide in this one.

So: require measurement to be available, then compare the full multiset of
codes. Both halves matter. The first catches a runner without fonts, the
second catches a change in behaviour that happens to keep the count the same.

Run from anywhere:  python research/assert_deck.py [deck.pptx]
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

from docx_integrity import check_pptx
from docx_integrity.fonts import measurement_available

#: What the committed deck is built to contain. Each shape in
#: research/build_pptx_corpus.py is named for its expected verdict, so this
#: list is derivable by hand - it is spelled out anyway, because a test that
#: recomputes its own expectation tests nothing.
EXPECTED = {
    "PPT001": 5,   # text taller than its box, autofit off
    "PPT003": 1,   # wrap="none" running past the slide
    "PPT004": 2,   # shape off the canvas
    "PPT005": 1,   # normAutofit shrinking text below readable size
    "PPT006": 1,   # two text shapes overlapping
    "PPT007": 1,   # font could not be resolved, paragraph not measured
}


def main(argv: list[str]) -> int:
    deck = Path(argv[1]) if len(argv) > 1 else Path("corpus/deck.pptx")
    if not deck.exists():
        print(f"assert_deck: no such deck: {deck}", file=sys.stderr)
        return 2

    ok, detail = measurement_available()
    print(f"measurement: {detail}")
    if not ok:
        print("::error::text measurement is unavailable, so this run proves "
              "nothing about layout - install metric-compatible fonts on the "
              "runner", file=sys.stderr)
        return 1

    findings = check_pptx(deck)
    got = collections.Counter(f.code for f in findings)

    for f in findings:
        print(f"  {f.code} {f.severity.value:5} {f.where}")

    if got == collections.Counter(EXPECTED):
        print(f"{deck}: reports exactly the {sum(EXPECTED.values())} expected "
              f"findings")
        return 0

    print("::error::the reference deck no longer reports what it was built "
          "to report", file=sys.stderr)
    for code in sorted(set(EXPECTED) | set(got)):
        want, have = EXPECTED.get(code, 0), got.get(code, 0)
        if want != have:
            print(f"  {code}: expected {want}, got {have}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
