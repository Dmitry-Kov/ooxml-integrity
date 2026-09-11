# Archive resource limits

An OOXML file is a ZIP archive, so reading it can require much more memory than
its size on disk suggests. The checker applies resource limits before
decompressing any member. This applies to DOCX self-consistency, PPTX layout,
and both files in a DOCX source comparison. The defaults leave room for ordinary
Office files and bound directory metadata, entry counts and expanded data.
Python object overhead and process RSS are not equal to these byte budgets.

## Defaults

| budget | default | config key |
| --- | ---: | --- |
| ZIP members | 4,096 | `max-entries` |
| compressed archive on disk | 256 MiB | `max-archive-bytes` |
| central directory, including names, extra fields and member comments | 16 MiB | `max-directory-bytes` |
| total declared expanded size | 512 MiB | `max-total-expanded-bytes` |
| one declared expanded member | 128 MiB | `max-entry-expanded-bytes` |
| expanded/compressed ratio per member | 1,000:1 | `max-compression-ratio` |

Before Python's ZIP reader loads the central directory, the checker:

1. Opens the file once and checks its byte size.
2. Reads at most 65,557 bytes for the end record and ZIP comment, plus fixed-size
   ZIP64 trailers when present. Validates directory sizes, offsets and counts
   for the supported layout below.
3. Enforces the directory byte budget and the declared entry limit. Scans actual
   directory records in 46-byte header reads, seeking past names, extra fields
   and comments without allocating them. The first record over `max-entries`
   fails immediately; otherwise the actual and declared counts must agree.

Only then does `ZipFile` allocate its index from the same open file handle.
For an unchanged input, it can create at most `max-entries` records from at most
`max-directory-bytes` of directory data. A forged small end-record count cannot
defer rejection until after the full index has been allocated. Callers must keep
the input file unchanged during the check.

The actual member count, every expanded size, their running total, and every
compression ratio are checked again before the first member is decompressed.
Exceeding a budget produces an error-level
`PKG007` finding. This classifies the input as too large for the configured
environment; it does not indicate an internal checker failure.

Package member names are percent-decoded and compared ASCII-case-insensitively,
as required by [OPC part-URI equivalence](https://learn.microsoft.com/en-us/dotnet/core/compatibility/core-libraries/8.0/system-io-packaging-case-insensitive-uri).
Absolute, traversal-like, backslash-separated, empty-segment, and duplicate
normalised names are rejected as `PKG008`. This prevents two ambiguous ZIP entries from
silently overwriting one another in the in-memory package map.

## Supported ZIP layout

The reader supports single-disk ZIP and ZIP64 archives with an ordinary central
directory. Stored/deflated members, data descriptors, member ZIP64 extra fields,
empty ZIPs and end-record comments up to 65,535 bytes are covered by regressions.
An empty ZIP can pass archive validation while failing DOCX/PPTX package checks.

Directory offsets must be absolute within the file, and the directory must end
exactly at its end record or ZIP64 trailer. ZIP64 uses the fixed 56-byte end
record followed by the 20-byte locator, with consistent legacy fields or their
ZIP64 sentinels. These structures follow
[PKWARE APPNOTE 6.3.10, sections 4.3.12–4.3.16](https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT).

Multi-disk archives, ZIP64 extensible end records, compressed/encrypted central
directories and ZIP directory signature records are outside this profile.
The checker does not repair offsets for concatenated or prepended data. Trailing
bytes, truncated metadata and conflicting offsets/counts are rejected as
`PKG002`. Comments containing an end-record signature are also outside the
supported profile: preflight must select the same trailer as Python's ZIP
reader, rather than validate a different apparent archive. This is a bounded
OOXML package reader, not validation of every ZIP extension.

## Configuration

Raise a limit when a trusted workload needs more room.
The keys work in `.ooxml-integrity.toml` or under `[tool.ooxml-integrity.archive]`
in `pyproject.toml`:

```toml
[archive]
max-entries = 4096
max-archive-bytes = 268435456
max-directory-bytes = 16777216
max-total-expanded-bytes = 536870912
max-entry-expanded-bytes = 134217728
max-compression-ratio = 1000.0
```

All byte values are integers. Every integer budget must be positive and the
ratio must be a finite number of at least `1`. Invalid or unknown archive keys
are reported as configuration errors.

Library callers can pass the same immutable policy explicitly:

```python
from ooxml_integrity import ArchiveLimits, check

limits = ArchiveLimits(max_total_expanded_bytes=256 * 1024 * 1024)
findings = check("report.docx", limits=limits)
```

The [browser demo](../demo/README.md) keeps these package defaults and adds a
25 MiB limit per input file and a 60-second timeout per check. It does not expose
archive-limit overrides.

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

These measurements describe this local run. Load time and peak allocation may
differ on other machines. In all cases, the configured totals bound the accepted
expanded data, and an over-budget archive is rejected before member
decompression.

### Central-directory rejection

Run `python research/measure_zip_directory.py` to generate small archives and
compare `package_names()` with an unguarded `ZipFile` index load. Both paths
count constructed `ZipInfo` objects; neither reads member bodies. Fixture
generation is outside the measured interval. The control represents the index
allocation allowed by the old declared-count preflight; the old checker still
rejected excessive actual counts afterwards.

Measured on 2026-09-12, macOS 26.6.2 arm64, CPython 3.9.6, with `tracemalloc`:

| actual / declared entries | directory bytes | unguarded peak Python bytes | guarded peak Python bytes | guarded ZipInfo count | guarded result |
| ---: | ---: | ---: | ---: | ---: | --- |
| 4,096 / 4,096 | 229,376 | 2,150,770 | 2,347,016 | 4,096 | accepted |
| 4,097 / 1 | 229,432 | 2,150,274 | 72,397 | 0 | `PKG007` |
| 10,000 / 1 | 560,000 | 5,177,387 | 72,397 | 0 | `PKG007` |
| 50,000 / 1 | 2,800,000 | 27,022,779 | 72,397 | 0 | `PKG007` |
| 1 / 1, long name/extra/comment | 180,060 | 368,084 | 72,397 | 0 | `PKG007`, 128 KiB directory budget |

These are allocation observations for this run, not universal RSS or timing
thresholds. The accepted boundary includes normal name validation overhead.
[Directory regressions](../tests/test_archive_directory.py) assert the structural
limits and rejection before index loading independently of machine memory use.
