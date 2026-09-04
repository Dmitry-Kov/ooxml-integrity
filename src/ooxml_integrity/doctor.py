"""Environment capability report for reproducible local and CI checks."""
from __future__ import annotations

import platform
import shutil
from importlib import metadata

from lxml import etree

from . import __version__
from .archive import DEFAULT_ARCHIVE_LIMITS
from .fonts import load_metrics


UNAVAILABLE_CHECKS = (
    {
        "id": "docx.fidelity.headers-footers",
        "reason": "header/footer source fidelity is not implemented yet",
    },
    {
        "id": "docx.header-footer-semantics",
        "reason": "header/footer Word semantics and layout are not inspected",
    },
    {
        "id": "docx.media-content",
        "reason": "embedded media bytes and visual rendering are not inspected",
    },
    {
        "id": "docx.strict-wordprocessingml",
        "reason": "Strict WordprocessingML namespaces are outside current rules",
    },
    {
        "id": "pptx.fidelity.source",
        "reason": "PPTX source comparison is not implemented",
    },
    {
        "id": "pptx.package-integrity",
        "reason": "the complete PPTX OPC relationship graph is not validated",
    },
    {
        "id": "pptx.slide-order",
        "reason": "presentation relationship order is not used for slide numbering",
    },
    {
        "id": "pptx.grouped-shapes",
        "reason": "group transforms are not composed",
    },
    {
        "id": "pptx.tables",
        "reason": "PowerPoint table text and geometry are not modelled",
    },
    {
        "id": "pptx.smartart",
        "reason": "SmartArt ownership and generated layout are not modelled",
    },
    {
        "id": "pptx.charts",
        "reason": "chart text and generated geometry are not modelled",
    },
    {
        "id": "pptx.fields",
        "reason": "DrawingML field values are not resolved",
    },
    {
        "id": "pptx.rotated-bounds",
        "reason": "rotation is not applied to collision or slide-edge bounds",
    },
    {
        "id": "pptx.vertical-text",
        "reason": "vertical text layout is not measured",
    },
    {
        "id": "pptx.master-layout-objects",
        "reason": "master-only and layout-only visible objects are not checked",
    },
)

FONT_PROBES = ("Calibri", "Arial", "Times New Roman")
_CONFIDENCE_RANK = {"exact": 0, "metric": 1, "similar": 2, "fallback": 3}


def _version(distribution: str) -> str:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return "unavailable"


def build_report() -> dict[str, object]:
    """Return a stable, JSON-ready capability report."""
    runtime = {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "lxml": ".".join(str(part) for part in etree.LXML_VERSION),
        "libxml2": ".".join(str(part) for part in etree.LIBXML_VERSION),
        "fonttools": _version("fonttools"),
    }
    limits = DEFAULT_ARCHIVE_LIMITS
    capabilities: list[dict[str, object]] = [
        {
            "id": "xml.safe-parser",
            "status": "available",
            "confidence": "exact",
            "detail": "DTD loading, entity expansion, network access, recovery "
                      "and huge-tree mode are disabled",
        },
        {
            "id": "archive.resource-limits",
            "status": "available",
            "confidence": "exact",
            "detail": (
                f"{limits.max_entries} entries; {limits.max_archive_bytes} archive "
                f"bytes; {limits.max_total_expanded_bytes} total expanded bytes; "
                f"{limits.max_entry_expanded_bytes} bytes per expanded entry; "
                f"{limits.max_compression_ratio:g}:1 compression ratio"
            ),
        },
    ]

    font_probes: list[dict[str, str]] = []
    font_failures: list[dict[str, str]] = []
    for requested in FONT_PROBES:
        try:
            face = load_metrics(requested).face
            font_probes.append({
                "requested": requested,
                "resolved_family": face.family,
                "path": str(face.path),
                "confidence": face.match,
            })
        except Exception as e:
            font_failures.append({"requested": requested, "reason": str(e)})

    if not font_probes:
        font_status = "unavailable"
        confidence = "unavailable"
    else:
        confidence = max(
            (probe["confidence"] for probe in font_probes),
            key=lambda value: _CONFIDENCE_RANK[value],
        )
        font_status = (
            "available"
            if not font_failures and confidence in ("exact", "metric")
            else "estimated"
        )
    capabilities.append({
        "id": "pptx.font-metrics",
        "status": font_status,
        "confidence": confidence,
        "detail": (
            f"{len(font_probes)}/{len(FONT_PROBES)} representative font "
            f"families are usable; fontconfig "
            f"{'available' if shutil.which('fc-match') else 'not installed'}"
        ),
    })

    return {
        "schema_version": 1,
        "version": __version__,
        "status": "ready" if font_status == "available" else "degraded",
        "runtime": runtime,
        "fonts": {
            "probes": font_probes,
            "failures": font_failures,
        },
        "capabilities": capabilities,
        "unavailable_checks": list(UNAVAILABLE_CHECKS),
    }
