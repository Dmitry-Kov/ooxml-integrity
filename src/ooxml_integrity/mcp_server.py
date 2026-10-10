"""Local MCP server, so an agent can check a document before returning it.

`ooxml-integrity mcp` speaks the Model Context Protocol over stdin and stdout:
JSON-RPC 2.0, one message per line. A tool server needs four methods of it -
`initialize`, `ping`, `tools/list` and `tools/call` - and those are small
enough to implement here, so the server adds no dependency and opens no
socket. It reads only the files a call names, on this machine; like the
agent's own file tools, it is not confined to the project directory.

Two tools, each one run of the CLI:

    check(path)                      ooxml-integrity check PATH --json --coverage
    compare(source, edited[, expect])
                                     ooxml-integrity check EDITED --against SOURCE
                                         --json --coverage

The checks are the CLI's own (`cli._run_one`, then config, expectations and
the JSON report through the same helpers), so the report is the one `--json`
prints. A one-line verdict comes first. Like the CLI it says `clean` only when
nothing was found and coverage has no estimated, skipped or unsupported
surface; otherwise `no findings in checked surfaces`.

The project config is found the way the CLI finds it, from the server's working
directory, or set with `--config` / `--no-config`, and it is read once, when the
server starts: the client starts it before the agent edits anything, so a
config the agent writes or edits afterwards cannot switch a rule off. A changed
config is named in the verdict, and so is every finding a config suppresses. A
call cannot change it either: an agent can declare the change it was asked to
make (`expect`), which is reported and fails when it did not happen.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, BinaryIO, Sequence

from . import __version__, cli
from .coverage import CoverageReport, coverage_for
from .expect import Expectation
from .finding import Finding, Severity
from .policy import ConfigError, Policy

#: Newest first. A client asking for another version gets the newest; tools
#: have the same shape in all of them, except that `structuredContent` arrived
#: in 2025-06-18.
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
STRUCTURED_SINCE = "2025-06-18"

PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS = (
    -32700, -32600, -32601, -32602)

INSTRUCTIONS = (
    "Checks .docx and .pptx files on this machine for structural defects and "
    "for review content an edit lost: comments, tracked changes, notes, "
    "headers. After editing a document, call compare with the original as "
    "source and your output as edited, and fix or report what it finds before "
    "returning the file. If the user asked for a change that removes something, "
    "such as accepting a tracked change, declare it in expect. Use check when "
    "there is no original. The verdict says 'clean' only when nothing was "
    "found and every surface was checked; 'no findings in checked surfaces' "
    "means part of the file was not assessed, listed under coverage."
)

_PATH = {"type": "string",
         "description": "path on this machine; absolute, or relative to the "
                        "server's working directory. URLs are rejected"}

TOOLS = [
    {
        "name": "check",
        "title": "Check a .docx or .pptx",
        "description": (
            "Self-check one .docx or .pptx: comment anchors, footnotes, styles, "
            "numbering, relationships and tracked-change markup in a document; "
            "text that overflows its box and shapes off the slide in a deck. "
            "Same as `ooxml-integrity check PATH --json --coverage`. Without "
            "the original it cannot see what an edit removed, such as a "
            "deleted comment: use compare when the original is available. "
            "Returns a one-line verdict, then the JSON report; exit_code 1 "
            "means findings at or above fail-on."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"path": _PATH},
            "required": ["path"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False,
                        "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "compare",
        "title": "Check an edited .docx against its original",
        "description": (
            "Everything check does on the edited file, plus what the edit lost "
            "relative to the original: comments, tracked insertions and "
            "deletions, footnotes and endnotes, headers and footers, text. Same "
            "as `ooxml-integrity check EDITED --against SOURCE --json "
            "--coverage`. For a .pptx only the layout checks run and the "
            "comparison is reported as not performed (FID000). If the user "
            "asked for a change that removes something, such as accepting or "
            "rejecting a tracked change or rewriting a header untracked, "
            "declare it in expect: a matching finding is reported as expected "
            "instead of failing, and an expectation nothing matches fails with "
            "EXP001."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {**_PATH, "description": "the original document; "
                           + _PATH["description"]},
                "edited": {**_PATH, "description": "the edited copy; "
                           + _PATH["description"]},
                "expect": {
                    "type": "array",
                    "description": (
                        "changes the edit was asked to make, as [[expect]] "
                        "entries in docs/configuration.md, without path"
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string",
                                     "description": "rule code, e.g. FID001"},
                            "reason": {"type": "string",
                                       "description": "why the change was "
                                                      "requested; required"},
                            "match": {
                                "type": "object",
                                "description": (
                                    "values the finding must carry: part, "
                                    "where, or keys of its extra, e.g. "
                                    '{"tag": "ins", "before": 2, "after": 1}'
                                ),
                            },
                            "required": {
                                "type": "boolean",
                                "description": "false allows the finding "
                                               "without requiring it; default "
                                               "true",
                            },
                        },
                        "required": ["code", "reason"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["source", "edited"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False,
                        "idempotentHint": True, "openWorldHint": False},
    },
]


class ToolError(Exception):
    """A call that cannot be run as asked; the agent sees the message."""


class _RpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# A scheme of two or more characters, so `C:\docs\a.docx` stays a path.
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]+:")


def local_path(value: Any, name: str) -> Path:
    """A regular file on this machine, or ToolError. Nothing is fetched."""
    if not isinstance(value, str) or not value:
        raise ToolError(f"{name} must be the path of a file on this machine")
    if "\x00" in value:
        raise ToolError(f"{name} contains a NUL character")
    if _SCHEME.match(value):
        raise ToolError(f"{name}: {value!r} is a URL; only files on this "
                        "machine are read, nothing is downloaded")
    if value.startswith(("\\\\", "//")):
        raise ToolError(f"{name}: {value!r} is a network path; only files on "
                        "this machine are read")
    path = Path(os.path.expanduser(value))
    if not path.exists():
        raise ToolError(f"{name}: file not found: {value} (relative paths "
                        f"resolve against {os.getcwd()})")
    if not path.is_file():
        raise ToolError(f"{name}: not a regular file: {value}")
    return path


def _expectations(entries: Any) -> list[Expectation]:
    """`expect` entries, validated as `[[expect]]` tables in a config are."""
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise ToolError("expect must be a list of objects with code and reason")
    for i, entry in enumerate(entries):
        if isinstance(entry, dict) and "path" in entry:
            raise ToolError(f"expect[{i}]: path is not used here; an "
                            "expectation in a call applies to its edited file")
    try:
        return Policy._from_dict({"expect": entries}).expectations
    except ConfigError as e:
        raise ToolError(str(e)) from None


def _codes(findings: list[Finding]) -> str:
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.code] = counts.get(f.code, 0) + 1
    return ", ".join(code if n == 1 else f"{code} ({n})"
                     for code, n in counts.items())


def _shown(path: str) -> str:
    """A config path as short as it can be said: relative when it is below the
    working directory."""
    try:
        relative = os.path.relpath(path)
    except ValueError:  # another drive on Windows
        return path
    return path if relative.startswith("..") else relative


def verdict(path: Path | str, findings: list[Finding], threshold: Severity,
            coverage: CoverageReport | None,
            expected: Sequence[tuple[Finding, str]] = (),
            hidden: Sequence[tuple[Finding, str]] = (),
            config: str = "", note: str = "") -> str:
    """One line: the CLI's summary head, then what it means at `threshold`."""
    line = cli._head(path, findings)
    failing = [f for f in findings if f.severity >= threshold]
    gaps = cli._has_gaps(coverage)
    if failing:
        line += f" - fails at fail-on {threshold.value}: {_codes(failing)}"
    elif findings:
        line += (f" - nothing at or above fail-on {threshold.value}; "
                 f"below it: {_codes(findings)}")
    else:
        line += " - no findings in checked surfaces" if gaps else " - clean"
    if expected:
        line += (f"; {len(expected)} finding(s) accepted as expected: "
                 f"{_codes([f for f, _ in expected])}")
    if hidden:
        line += (f"; {len(hidden)} finding(s) suppressed by config"
                 + (f" {_shown(config)}" if config else "")
                 + f": {_codes([f for f, _ in hidden])}")
    if note:
        line += f"; {note}"
    if gaps:
        counts = coverage.summary()
        line += "; not fully checked: " + ", ".join(
            f"{counts[s.value]} {s.value}" for s in cli.GAP_STATUSES
            if counts[s.value]
        ) + " (see coverage)"
    return line


class Server:
    def __init__(self, *, config: str | None = None, no_config: bool = False,
                 fail_on: Severity | None = None) -> None:
        self.config = config
        self.no_config = no_config
        self.fail_on = fail_on
        self.protocol: str | None = None
        # Read once, before the agent edits anything; see the module docstring.
        self.policy, self.config_error = self._load_policy()

    def _load_policy(self) -> tuple[Policy | None, str | None]:
        if self.no_config:
            return Policy(), None
        try:
            return Policy.load(self.config), None
        except ConfigError as e:
            return None, str(e)

    def _config_note(self) -> str:
        """Say so when the config on disk is not the one read at start."""
        if self.no_config or self._load_policy() == (self.policy, self.config_error):
            return ""
        return ("config changed since the server started; the one read at "
                "start was used")

    # ------------------------------------------------------------ tools
    def run(self, edited_arg: Any, source_arg: Any = None,
            expect_arg: Any = None, *, edited_name: str = "path") -> dict:
        """One CLI run on one file; returns verdict, exit_code and report."""
        edited = local_path(edited_arg, edited_name)
        source = (local_path(source_arg, "source")
                  if source_arg is not None else None)
        if self.config_error:
            raise ToolError(f"config: {self.config_error} (read when the server "
                            "started; restart it after fixing the file)")
        policy = self.policy
        threshold = self.fail_on or policy.fail_on
        expectations = policy.expectations + _expectations(expect_arg)

        findings = cli._run_one(edited, source, policy.archive)
        coverage = coverage_for(edited, findings, source=source,
                                limits=policy.archive)
        kept, hidden, matched = cli._apply_policy(
            edited, findings, policy, expectations, None)
        report = cli._json_payload(
            [cli._json_file(edited, kept, hidden, matched,
                            expectations=bool(expectations),
                            coverage=coverage)],
            threshold, policy, None,
        )
        failed = cli._fails(kept, threshold)
        return {
            "verdict": verdict(edited, kept, threshold, coverage,
                               matched, hidden, policy.source,
                               self._config_note()),
            "exit_code": cli.EXIT_FINDINGS if failed else cli.EXIT_OK,
            "report": report,
        }

    def _tool(self, name: str, args: dict) -> dict:
        if name == "check":
            return self.run(args.get("path"))
        return self.run(args.get("edited"), args.get("source"),
                        args.get("expect"), edited_name="edited")

    def call(self, params: dict) -> dict:
        name = params.get("name")
        if name not in ("check", "compare"):
            raise _RpcError(INVALID_PARAMS, f"unknown tool: {name!r}")
        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            raise _RpcError(INVALID_PARAMS, "arguments must be an object")
        schema = next(t for t in TOOLS if t["name"] == name)["inputSchema"]
        unknown = sorted(set(args) - set(schema["properties"]))
        try:
            if unknown:
                raise ToolError(f"{name} does not take: {', '.join(unknown)}")
            if name == "compare" and args.get("source") is None:
                raise ToolError("compare needs source, the original document")
            outcome = self._tool(name, args)
        except ToolError as e:
            return {"content": [{"type": "text", "text": str(e)}],
                    "isError": True}
        except Exception as e:  # a checker bug must not end the session
            return {"content": [{"type": "text", "text":
                                 f"internal error: {type(e).__name__}: {e}"}],
                    "isError": True}
        result = {
            "content": [
                {"type": "text", "text": outcome["verdict"]},
                {"type": "text",
                 "text": json.dumps(outcome["report"], indent=2,
                                    ensure_ascii=True)},
            ],
            "isError": False,
        }
        if self.protocol is not None and self.protocol >= STRUCTURED_SINCE:
            result["structuredContent"] = outcome
        return result

    # ------------------------------------------------------------ protocol
    def initialize(self, params: dict) -> dict:
        asked = params.get("protocolVersion")
        self.protocol = (asked if asked in PROTOCOL_VERSIONS
                         else PROTOCOL_VERSIONS[0])
        return {
            "protocolVersion": self.protocol,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "ooxml-integrity", "version": __version__},
            "instructions": INSTRUCTIONS,
        }

    def handle(self, message: Any) -> dict | None:
        """The reply to one decoded message, or None for a notification."""
        if isinstance(message, list):
            return _error(None, INVALID_REQUEST, "batches are not supported")
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _error(None, INVALID_REQUEST, "not a JSON-RPC 2.0 message")
        method, rid = message.get("method"), message.get("id")
        if not isinstance(method, str):
            if "result" in message or "error" in message:
                return None  # a response; this server sends no requests
            return _error(rid, INVALID_REQUEST, "method must be a string")
        if "id" not in message:
            return None  # notifications/initialized, cancelled, ...
        params = message.get("params") or {}
        if not isinstance(params, dict):
            return _error(rid, INVALID_PARAMS, "params must be an object")
        try:
            if method == "initialize":
                result = self.initialize(params)
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                result = self.call(params)
            else:
                raise _RpcError(METHOD_NOT_FOUND, f"method not found: {method}")
        except _RpcError as e:
            return _error(rid, e.code, e.message)
        return {"jsonrpc": "2.0", "id": rid, "result": result}


def _error(rid: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": code, "message": message}}


def serve(stdin: BinaryIO | None = None, stdout: BinaryIO | None = None,
          **options: Any) -> int:
    """Answer messages from `stdin` until it closes."""
    stdin = stdin if stdin is not None else sys.stdin.buffer
    out = stdout if stdout is not None else sys.stdout.buffer
    server = Server(**options)
    # Only protocol messages may reach stdout; anything printed during a
    # check goes to stderr, which clients show as the server's log.
    saved, sys.stdout = sys.stdout, sys.stderr
    try:
        for raw in stdin:
            if not raw.strip():
                continue
            try:
                message = json.loads(raw)
            except ValueError as e:
                reply = _error(None, PARSE_ERROR, f"parse error: {e}")
            else:
                reply = server.handle(message)
            if reply is not None:
                out.write(json.dumps(reply, ensure_ascii=True).encode("ascii")
                          + b"\n")
                out.flush()
    finally:
        sys.stdout = saved
    return cli.EXIT_OK
