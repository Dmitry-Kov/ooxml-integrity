"""
docx-integrity - structural integrity checks for .docx files.

Two questions, both needed:

    check(path)               is this .docx self-consistent?
    compare(source, edited)   what did the edit lose relative to the source?
    check_pptx(path)          does this deck's text fit, and do shapes collide?

None of them needs a model, a renderer, or the network.

    >>> from docx_integrity import check, compare
    >>> for f in check("edited.docx"):
    ...     print(f)
    >>> for f in compare("original.docx", "edited.docx"):
    ...     print(f)
"""
from .fidelity import TRACKED, compare
from .finding import ERROR, INFO, WARN, Finding, Severity, summarize, worst
from .inspector import Inspector, check, check_many
from .pptx_checks import check_pptx

__version__ = "0.1.2"

__all__ = [
    "check",
    "check_many",
    "check_pptx",
    "compare",
    "Inspector",
    "Finding",
    "Severity",
    "ERROR",
    "WARN",
    "INFO",
    "summarize",
    "worst",
    "TRACKED",
    "__version__",
]
