"""Config, suppressions and baseline: the part that makes this deployable.

Everything else in this package answers "what is wrong with this file". This
module answers the question a person hits ten minutes after adding the check to
a real repository: *how do I turn off the one rule that does not apply to us,
without turning off the tool?*

Three mechanisms, in order of how blunt they are.

**Severity overrides.** A rule can be lowered, raised, or set to `off`. Use it
when a rule is systematically wrong for a project - the usual case is `PPT006`
(overlapping shapes) in decks where shapes overlap by design.

**Ignores.** A rule off for a path glob, with a reason. Narrower than an
override, and the reason is required, because a suppression whose justification
lives in someone's memory is a suppression nobody can review later.

**Baseline.** A snapshot of what a repository already reports, so the check
fails only on what is *new*. This is what lets an existing project adopt the
tool at all: nobody fixes two hundred findings before they can gate the next
commit.

The three are deliberately separate. An override says "this rule is wrong for
us", an ignore says "this rule is wrong here", and a baseline says "we know, not
today". Collapsing them into one switch loses which of the three someone meant.

Findings themselves are never altered by policy - `check()` and `compare()` stay
pure and keep reporting what they see. Policy is applied afterwards, so a JSON
or SARIF report can carry the suppressed findings too, marked as suppressed,
rather than pretending they were never there.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .finding import Finding, Severity

#: File names looked for, in order, when no config is given explicitly. The
#: `.docx-integrity.toml` spelling is the name this project shipped under before
#: it also checked decks; it is still read, because a rename on our side is not
#: a reason for someone else's config to stop working.
CONFIG_NAMES = (".ooxml-integrity.toml", ".docx-integrity.toml", "pyproject.toml")

#: Where a baseline is written by default.
DEFAULT_BASELINE = ".ooxml-integrity-baseline.json"

#: Baseline fingerprints changed in v2 so distinct fidelity losses cannot
#: consume one another's allowance. Old baselines must be regenerated rather
#: than silently interpreted with the old, collision-prone identity.
BASELINE_VERSION = 2

#: Tables read out of pyproject.toml, in order. Same reasoning as above.
PYPROJECT_TABLES = (("tool", "ooxml-integrity"), ("tool", "docx-integrity"))

#: `off` is not a Severity: it means the finding is dropped, not downgraded.
OFF = "off"


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:  # pragma: no cover - exercised on 3.9/3.10
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ModuleNotFoundError:
            raise ConfigError(
                f"{path} needs a TOML parser on Python < 3.11. "
                "Install it with: pip install tomli"
            ) from None
    with open(path, "rb") as fh:
        return tomllib.load(fh)


class ConfigError(Exception):
    """A config file that cannot be honoured. Never guessed around."""


@dataclass(frozen=True)
class Ignore:
    code: str
    path: str = "**"
    reason: str = ""

    def covers(self, code: str, file: str) -> bool:
        if self.code != code and self.code != "*":
            return False
        return _match(file, self.path)


def _match(file: str, pattern: str) -> bool:
    """Glob match on a posix-style relative path, with `**` meaning any depth.

    `fnmatch` alone treats `*` as crossing directory separators, which makes
    `decks/*.pptx` match `decks/a/b.pptx` - surprising in a config file where
    people expect shell semantics. So `**` is translated explicitly and `*` is
    kept within one segment.
    """
    f = PurePosixPath(str(file).replace(os.sep, "/")).as_posix().lstrip("./")
    p = pattern.replace(os.sep, "/").lstrip("./")
    if p in ("**", "*"):
        return True
    # a bare directory prefix means everything under it
    if p.endswith("/"):
        p += "**"
    parts = p.split("**")
    if len(parts) == 1:
        segs_f, segs_p = f.split("/"), p.split("/")
        if len(segs_f) != len(segs_p):
            return False
        return all(fnmatch.fnmatch(a, b) for a, b in zip(segs_f, segs_p))
    # with `**` present, fall back to fnmatch over the whole path, which is
    # what people mean by `decks/**/*.pptx`
    return fnmatch.fnmatch(f, p.replace("**/", "*").replace("**", "*"))


@dataclass
class Policy:
    """What a project has decided about the rules."""

    fail_on: Severity = Severity.ERROR
    severity: dict[str, str] = field(default_factory=dict)
    ignores: list[Ignore] = field(default_factory=list)
    source: str = ""

    # ------------------------------------------------------------------ load
    @classmethod
    def load(cls, explicit: str | os.PathLike | None = None,
             start: str | os.PathLike = ".") -> "Policy":
        """Read config from `explicit`, or find one by walking up from `start`.

        A path given explicitly must exist: silently falling back to defaults
        when someone points at a config that is not there is how a project ends
        up thinking a rule is off when it is on.
        """
        if explicit is not None:
            p = Path(explicit)
            if not p.exists():
                raise ConfigError(f"config file not found: {p}")
            return cls._from_file(p)

        here = Path(start).resolve()
        for d in (here, *here.parents):
            for name in CONFIG_NAMES:
                p = d / name
                if p.is_file():
                    got = cls._from_file(p, required=False)
                    if got is not None:
                        return got
        return cls()

    @classmethod
    def _from_file(cls, path: Path, required: bool = True) -> "Policy | None":
        raw = _load_toml(path)
        data = raw
        if path.name == "pyproject.toml":
            data = {}
            for table in PYPROJECT_TABLES:
                node = raw
                for key in table:
                    node = node.get(key, {}) if isinstance(node, dict) else {}
                if node:
                    data = node
                    break
            if not data:
                if required:
                    raise ConfigError(
                        f"{path} has no [tool.ooxml-integrity] section")
                return None
        return cls._from_dict(data, source=str(path))

    @classmethod
    def _from_dict(cls, data: dict[str, Any], source: str = "") -> "Policy":
        unknown = set(data) - {"fail-on", "fail_on", "severity", "ignore"}
        if unknown:
            raise ConfigError(
                f"unknown key(s) in config: {', '.join(sorted(unknown))}. "
                "Expected: fail-on, severity, ignore"
            )
        raw = data.get("fail-on", data.get("fail_on", "error"))
        try:
            fail_on = Severity.parse(str(raw))
        except ValueError as e:
            raise ConfigError(f"fail-on: {e}") from None

        sev = {}
        for code, value in (data.get("severity") or {}).items():
            v = str(value).strip().lower()
            if v != OFF:
                try:
                    Severity.parse(v)
                except ValueError as e:
                    raise ConfigError(f"severity.{code}: {e} (or 'off')") from None
            sev[code.upper()] = v

        ignores = []
        for i, entry in enumerate(data.get("ignore") or []):
            if not isinstance(entry, dict) or "code" not in entry:
                raise ConfigError(
                    f"ignore[{i}] needs at least a 'code' key")
            reason = str(entry.get("reason", "")).strip()
            if not reason:
                raise ConfigError(
                    f"ignore[{i}] ({entry['code']}) has no 'reason'. A "
                    "suppression without a written reason cannot be reviewed "
                    "later, so it is not accepted."
                )
            ignores.append(Ignore(code=str(entry["code"]).upper(),
                                  path=str(entry.get("path", "**")),
                                  reason=reason))
        return cls(fail_on=fail_on, severity=sev, ignores=ignores, source=source)

    # ------------------------------------------------------------------ apply
    def apply(self, file: str, findings: Iterable[Finding]
              ) -> tuple[list[Finding], list[tuple[Finding, str]]]:
        """Returns (kept, [(suppressed, why)]) with severities already adjusted."""
        kept: list[Finding] = []
        dropped: list[tuple[Finding, str]] = []
        for f in findings:
            override = self.severity.get(f.code)
            if override == OFF:
                dropped.append((f, f"severity.{f.code} = off"))
                continue
            hit = next((i for i in self.ignores if i.covers(f.code, file)), None)
            if hit is not None:
                dropped.append((f, f"ignore {hit.code} in {hit.path}: {hit.reason}"))
                continue
            if override:
                f = Finding(f.code, Severity.parse(override), f.message,
                            f.where, f.part, f.extra)
            kept.append(f)
        return kept, dropped


# ---------------------------------------------------------------- baseline
def fingerprint(file: str, f: Finding) -> str:
    """Identity of a finding across runs.

    Deliberately excludes the message. Messages carry measurements - "text needs
    118pt in a 48pt box" - and a baseline keyed on those would go stale the
    moment anything moved by a point, which is the opposite of what a baseline
    is for. Path, code and location are the general identity. Fidelity findings
    also need one stable discriminator: their construct tag, or a digest of the
    lost body. The digest distinguishes bodies without writing document content
    into a baseline that is normally committed to source control.
    """
    where = f.where or f.part
    stable = ""
    if f.code in ("FID001", "FID002"):
        tag = f.extra.get("tag")
        if tag:
            stable = f"tag={tag}"
    elif f.code in ("FID004", "FID005", "FID006"):
        body = f.extra.get("body")
        if isinstance(body, str) and body:
            digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
            stable = f"body-sha256={digest}"

    key = f"{str(file).replace(os.sep, '/')}::{f.code}::{where}"
    return f"{key}::{stable}" if stable else key


def make_baseline(results: dict[str, list[Finding]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for file, findings in results.items():
        for f in findings:
            key = fingerprint(file, f)
            counts[key] = counts.get(key, 0) + 1
    return {
        "version": BASELINE_VERSION,
        "note": ("Findings recorded as already present. The check fails only on "
                 "new ones. Regenerate with --write-baseline after fixing some."),
        "findings": dict(sorted(counts.items())),
    }


def read_baseline(path: str | os.PathLike) -> dict[str, int]:
    p = Path(path)
    if not p.exists():
        raise ConfigError(
            f"baseline not found: {p}. Create one with --write-baseline {p}")
    with open(p, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or "findings" not in data:
        raise ConfigError(f"{p} is not a ooxml-integrity baseline")
    version = data.get("version")
    if type(version) is int and version == 1:
        raise ConfigError(
            f"{p} uses baseline version 1, whose fidelity fingerprints can hide "
            "a different new loss. Regenerate it with the same check command "
            f"and --write-baseline {p}"
        )
    if type(version) is not int or version != BASELINE_VERSION:
        raise ConfigError(
            f"{p} uses unsupported baseline version {version!r}; this release "
            f"supports version {BASELINE_VERSION}. Regenerate it with the same "
            f"check command and --write-baseline {p}"
        )
    return {str(k): int(v) for k, v in data["findings"].items()}


def apply_baseline(file: str, findings: list[Finding], allowance: dict[str, int]
                   ) -> tuple[list[Finding], list[tuple[Finding, str]]]:
    """Drop findings the baseline already accounts for, one per recorded count.

    Counting rather than set membership: if a shape had one overflow recorded
    and now has two, the second is new and must be reported. A set would hide
    it.
    """
    kept: list[Finding] = []
    dropped: list[tuple[Finding, str]] = []
    for f in findings:
        key = fingerprint(file, f)
        if allowance.get(key, 0) > 0:
            allowance[key] -= 1
            dropped.append((f, "in baseline"))
        else:
            kept.append(f)
    return kept, dropped
