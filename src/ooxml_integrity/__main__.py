"""Entry point for `python -m ooxml_integrity`.

The console script `ooxml-integrity` lands in pip's scripts directory, which is
not on PATH on plenty of machines - a `pip install --user` against a Python
whose user base nobody added to PATH is the common case, and pip only warns
about it. `python -m ooxml_integrity` works there without editing any shell
config, and it also removes the ambiguity of which interpreter's install you are
running when several are present.
"""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
