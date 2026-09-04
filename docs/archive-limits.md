# Archive resource limits

Every supported entry point validates an OOXML ZIP before it decompresses a
member: DOCX self-consistency, PPTX layout, and both sides of a DOCX source
comparison. The defaults are deliberately conservative enough for ordinary
Office files while placing a finite ceiling on memory and decompression work.

## Defaults

| budget | default | config key |
| --- | ---: | --- |
| ZIP members | 4,096 | `max-entries` |
| compressed archive on disk | 256 MiB | `max-archive-bytes` |
| total declared expanded size | 512 MiB | `max-total-expanded-bytes` |
| one declared expanded member | 128 MiB | `max-entry-expanded-bytes` |
| expanded/compressed ratio per member | 1,000:1 | `max-compression-ratio` |

The archive byte size and declared EOCD entry count are checked before Python's
ZIP reader loads the central directory. The actual member count, every expanded
size, their running total, and every compression ratio are then checked before
the first member body is decompressed. A budget failure is an error-level
`PKG007` finding; it is invalid input for the configured environment, not an
internal checker failure.

Package member names are percent-decoded and compared ASCII-case-insensitively,
as required by [OPC part-URI equivalence](https://learn.microsoft.com/en-us/dotnet/core/compatibility/core-libraries/8.0/system-io-packaging-case-insensitive-uri).
Absolute,
traversal-like, backslash-separated, empty-segment, and duplicate normalised
names are rejected as `PKG008`. This prevents two ambiguous ZIP entries from
silently overwriting one another in the in-memory package map.

## Configuration

Override a limit only when a trusted workload genuinely needs more headroom.
The keys work in `.ooxml-integrity.toml` or under `[tool.ooxml-integrity.archive]`
in `pyproject.toml`:

```toml
[archive]
max-entries = 4096
max-archive-bytes = 268435456
max-total-expanded-bytes = 536870912
max-entry-expanded-bytes = 134217728
max-compression-ratio = 1000.0
```

All byte values are integers. Every integer budget must be positive and the
ratio must be a finite number of at least `1`. Invalid or unknown archive keys
are configuration errors; the checker does not guess around them.

Library callers can pass the same immutable policy explicitly:

```python
from ooxml_integrity import ArchiveLimits, check

limits = ArchiveLimits(max_total_expanded_bytes=256 * 1024 * 1024)
findings = check("report.docx", limits=limits)
```

## Reproducible measurement

`research/measure_archive_limits.py` reports elapsed load time and peak Python
allocation for a supplied package. With no path it creates one stored 64 MiB
member, so the result measures the large-entry path without committing a large
fixture.

Measurements on 2026-09-04, macOS, CPython 3.9, warm local filesystem:

| input | entries | expanded | elapsed | peak Python allocation |
| --- | ---: | ---: | ---: | ---: |
| `corpus/base.docx` | 14 | 15.9 KiB | 0.8 ms | 109.4 KiB |
| `corpus/deck.pptx` | 46 | 109.9 KiB | 2.0 ms | 224.7 KiB |
| generated stored member | 1 | 64 MiB | 10.4 ms | 64.0 MiB |

These are a reproducible local observation, not a cross-platform performance
guarantee. The important invariant is that accepted expanded data is bounded by
the configured totals and an over-budget archive is rejected before member
decompression.
