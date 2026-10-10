"""MCP server: driven over stdio the way an agent's client drives it.

The tool results must be the CLI's own reports, so most tests compare a call
with `check --json --coverage` on the same committed fixtures.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys

import pytest
from conftest import ROOT, run_cli

from ooxml_integrity import __version__, cli
from ooxml_integrity.coverage import CoverageItem, CoverageReport, CoverageStatus
from ooxml_integrity.mcp_server import PROTOCOL_VERSIONS, serve, verdict
from ooxml_integrity.finding import Severity

FAST = "runs/t4_fast_fee/agreement.docx"
CAREFUL = "runs/t2_pres/agreement.docx"
BASE = "corpus/base.docx"
DECK = "corpus/deck.pptx"


def init(version: str = "2025-06-18") -> dict:
    return {"jsonrpc": "2.0", "id": 0, "method": "initialize",
            "params": {"protocolVersion": version, "capabilities": {},
                       "clientInfo": {"name": "pytest", "version": "0"}}}


INITIALIZED = {"jsonrpc": "2.0", "method": "notifications/initialized"}


def call(name: str, arguments: dict, rid: int = 1) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "method": "tools/call",
            "params": {"name": name, "arguments": arguments}}


def exchange(*messages, args=("--no-config",), cwd=ROOT):
    """Send every message, close stdin, return the decoded replies.

    Decoding every stdout line as JSON is itself the check that nothing but
    protocol messages reaches stdout.
    """
    text = "".join((m if isinstance(m, str) else json.dumps(m)) + "\n"
                   for m in messages)
    r = subprocess.run(
        [sys.executable, "-m", "ooxml_integrity", "mcp", *args],
        input=text, capture_output=True, text=True, cwd=cwd, timeout=300,
    )
    assert r.returncode == cli.EXIT_OK, r.stderr
    return [json.loads(line) for line in r.stdout.splitlines()]


def tool(name: str, arguments: dict, *, version: str = "2025-06-18",
         args=("--no-config",), cwd=ROOT) -> dict:
    replies = exchange(init(version), INITIALIZED, call(name, arguments),
                       args=args, cwd=cwd)
    assert [r["id"] for r in replies] == [0, 1], replies
    return replies[1]["result"]


def cli_report(*args: str) -> tuple[dict, int]:
    r = run_cli("check", *args, "--json", "--coverage", "--no-config")
    return json.loads(r.stdout), r.returncode


# ------------------------------------------------------------------ protocol
def test_initialize_negotiates_the_protocol_version():
    replies = exchange(init("2025-06-18"), INITIALIZED,
                       {**init("2099-01-01"), "id": 1})
    # the notification gets no reply
    assert [r["id"] for r in replies] == [0, 1]
    first, unknown = (r["result"] for r in replies)
    assert first["protocolVersion"] == "2025-06-18"
    assert unknown["protocolVersion"] == PROTOCOL_VERSIONS[0]
    assert first["serverInfo"] == {"name": "ooxml-integrity",
                                   "version": __version__}
    assert first["capabilities"] == {"tools": {"listChanged": False}}
    assert "compare" in first["instructions"]


def test_tools_list_describes_both_tools():
    replies = exchange(init(), INITIALIZED,
                       {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    tools = {t["name"]: t for t in replies[1]["result"]["tools"]}
    assert sorted(tools) == ["check", "compare"]
    assert tools["check"]["inputSchema"]["required"] == ["path"]
    assert tools["compare"]["inputSchema"]["required"] == ["source", "edited"]
    expect_item = tools["compare"]["inputSchema"]["properties"]["expect"]["items"]
    assert expect_item["required"] == ["code", "reason"]
    for t in tools.values():
        assert t["annotations"]["readOnlyHint"] is True
        assert t["annotations"]["openWorldHint"] is False


def test_protocol_errors_do_not_end_the_session():
    replies = exchange(
        init(), INITIALIZED,
        "this is not json",
        [{"jsonrpc": "2.0", "id": 1, "method": "ping"}],
        {"jsonrpc": "2.0", "id": 2, "method": "resources/list"},
        call("delete", {"path": BASE}, rid=3),
        {"jsonrpc": "2.0", "id": 4, "method": "ping"},
        {"jsonrpc": "2.0", "id": 5, "result": {}},  # a stray response
    )
    by_id = {}
    for r in replies[1:]:
        by_id.setdefault(r["id"], []).append(r)
    errors = [r["error"]["code"] for r in by_id[None]]
    assert errors == [-32700, -32600]  # parse error, then the batch
    assert by_id[2][0]["error"]["code"] == -32601
    assert by_id[3][0]["error"]["code"] == -32602
    assert by_id[4][0]["result"] == {}
    assert 5 not in by_id


def test_end_of_input_ends_the_server():
    r = subprocess.run([sys.executable, "-m", "ooxml_integrity", "mcp"],
                       input="", capture_output=True, text=True, cwd=ROOT,
                       timeout=120)
    assert (r.returncode, r.stdout) == (cli.EXIT_OK, "")


def test_text_a_check_prints_goes_to_stderr(monkeypatch, capsys):
    def noisy(path, source, limits):
        print("stray output from a check")
        return []

    monkeypatch.setattr(cli, "_run_one", noisy)
    out = io.BytesIO()
    lines = [init(), call("check", {"path": str(ROOT / BASE)})]
    serve(io.BytesIO(b"".join(json.dumps(m).encode() + b"\n" for m in lines)),
          out, no_config=True)
    replies = [json.loads(x) for x in out.getvalue().splitlines()]
    assert [r["id"] for r in replies] == [0, 1]
    assert "stray output from a check" in capsys.readouterr().err


@pytest.mark.parametrize("flags", [("--fail-on", "fatal"),
                                   ("--config", "no-such-config.toml")])
def test_bad_server_flags_are_usage_errors(flags):
    r = subprocess.run([sys.executable, "-m", "ooxml_integrity", "mcp", *flags],
                       input="", capture_output=True, text=True, cwd=ROOT,
                       timeout=120)
    assert r.returncode == cli.EXIT_USAGE
    assert r.stdout == ""


# ------------------------------------------------------------------ tools
def test_compare_is_check_against_with_json_and_coverage(runs_dir, base_docx):
    result = tool("compare", {"source": BASE, "edited": FAST})
    expected, code = cli_report(FAST, "--against", BASE)
    structured = result["structuredContent"]
    assert structured["report"] == expected
    assert structured["exit_code"] == code == cli.EXIT_FINDINGS
    assert result["isError"] is False

    verdict_text, report_text = (c["text"] for c in result["content"])
    assert json.loads(report_text) == expected
    assert verdict_text == structured["verdict"]
    assert verdict_text.startswith(
        f"{FAST}: 2 error(s), 0 warning(s), 1 info - fails at fail-on error: "
        "CMT005, FID001")
    assert "not fully checked: 2 unsupported" in verdict_text
    assert "clean" not in verdict_text


@pytest.mark.parametrize("path,code", [(BASE, cli.EXIT_OK),
                                       (DECK, cli.EXIT_FINDINGS)])
def test_check_is_check_with_json_and_coverage(base_docx, path, code):
    result = tool("check", {"path": path})
    expected, exit_code = cli_report(path)
    assert result["structuredContent"]["report"] == expected
    assert result["structuredContent"]["exit_code"] == exit_code == code


def test_self_check_never_says_clean(base_docx):
    # Without a source the fidelity surfaces are skipped, so a file with no
    # findings is described the way `check --coverage` describes it.
    text = tool("check", {"path": BASE})["content"][0]["text"]
    assert text == (
        f"{BASE}: 0 error(s), 0 warning(s), 0 info - no findings in checked "
        "surfaces; not fully checked: 6 skipped, 2 unsupported (see coverage)")


def test_clean_only_when_every_surface_was_checked(tmp_path):
    docx = pytest.importorskip("docx")
    doc = docx.Document()
    doc.add_paragraph("Nothing here needs a header, a picture or a source.")
    plain = tmp_path / "plain.docx"
    doc.save(plain)
    result = tool("compare", {"source": str(plain), "edited": str(plain)})
    assert result["content"][0]["text"] == (
        f"{plain}: 0 error(s), 0 warning(s), 0 info - clean")
    gaps = result["structuredContent"]["report"]["files"][0]["coverage"]
    assert gaps["summary"]["skipped"] == gaps["summary"]["unsupported"] == 0


def test_verdict_names_findings_below_the_threshold():
    from ooxml_integrity.finding import Finding

    checked = CoverageReport((CoverageItem("x", CoverageStatus.CHECKED, ""),))
    estimated = CoverageReport((
        CoverageItem("x", CoverageStatus.CHECKED, ""),
        CoverageItem("y", CoverageStatus.ESTIMATED, ""),
    ))
    warn = Finding("TXT002", Severity.WARN, "literal entity")
    assert verdict("a.docx", [warn], Severity.ERROR, checked) == (
        "a.docx: 0 error(s), 1 warning(s), 0 info - nothing at or above "
        "fail-on error; below it: TXT002")
    assert verdict("a.docx", [], Severity.ERROR, estimated) == (
        "a.docx: 0 error(s), 0 warning(s), 0 info - no findings in checked "
        "surfaces; not fully checked: 1 estimated (see coverage)")


def test_pptx_compare_says_the_comparison_was_not_performed():
    result = tool("compare", {"source": DECK, "edited": DECK})
    expected, code = cli_report(DECK, "--against", DECK)
    assert result["structuredContent"]["report"] == expected
    codes = [f["code"] for f in expected["files"][0]["findings"]]
    assert "FID000" in codes
    assert "FID000" in result["content"][0]["text"]


def test_fail_on_flag_reaches_the_verdict(runs_dir, base_docx):
    lenient = tool("compare", {"source": BASE, "edited": CAREFUL})
    strict = tool("compare", {"source": BASE, "edited": CAREFUL},
                  args=("--no-config", "--fail-on", "info"))
    assert lenient["structuredContent"]["exit_code"] == cli.EXIT_OK
    assert "nothing at or above fail-on error" in lenient["content"][0]["text"]
    assert strict["structuredContent"]["exit_code"] == cli.EXIT_FINDINGS
    assert strict["structuredContent"]["report"]["fail_on"] == "info"
    assert "fails at fail-on info: FID002 (2), FID012 (2)" in (
        strict["content"][0]["text"])


def test_structured_content_needs_2025_06_18(base_docx):
    old = tool("check", {"path": BASE}, version="2025-03-26")
    assert "structuredContent" not in old
    assert json.loads(old["content"][1]["text"])["files"][0]["path"] == BASE


def test_config_is_found_from_the_server_working_directory(tmp_path, runs_dir,
                                                           base_docx):
    (tmp_path / ".ooxml-integrity.toml").write_text(
        '[[ignore]]\ncode = "CMT005"\nreason = "known in this fixture"\n')
    result = tool("compare", {"source": str(ROOT / BASE),
                              "edited": str(ROOT / FAST)},
                  args=(), cwd=tmp_path)
    report = result["structuredContent"]["report"]
    assert report["config"].endswith(".ooxml-integrity.toml")
    assert [f["code"] for f in report["files"][0]["suppressed"]] == ["CMT005"]
    assert "1 finding(s) suppressed by config" in result["content"][0]["text"]


# ------------------------------------------------------------------ expect
def test_expect_accepts_the_requested_change_only(runs_dir, base_docx):
    result = tool("compare", {"source": BASE, "edited": FAST, "expect": [
        {"code": "FID001", "reason": "the task removed one comment",
         "match": {"tag": "commentReference", "before": 2, "after": 1}},
    ]})
    entry = result["structuredContent"]["report"]["files"][0]
    assert [f["code"] for f in entry["expected"]] == ["FID001"]
    assert entry["expected"][0]["expected_because"] == (
        "FID001 tag=commentReference before=2 after=1: "
        "the task removed one comment")
    # the orphaned comment left behind still fails the run
    assert [f["code"] for f in entry["findings"]] == ["CMT005", "FID002"]
    assert result["structuredContent"]["exit_code"] == cli.EXIT_FINDINGS
    assert "1 finding(s) accepted as expected: FID001" in (
        result["content"][0]["text"])


def test_an_expectation_nothing_matches_fails(base_docx):
    result = tool("compare", {"source": BASE, "edited": BASE, "expect": [
        {"code": "FID001", "reason": "the task accepts one insertion",
         "match": {"tag": "ins"}},
    ]})
    entry = result["structuredContent"]["report"]["files"][0]
    assert [f["code"] for f in entry["findings"]] == ["EXP001"]
    assert result["structuredContent"]["exit_code"] == cli.EXIT_FINDINGS


@pytest.mark.parametrize("expect,message", [
    ([{"code": "FID001"}], "has no 'reason'"),
    ([{"code": "FID001", "reason": "r", "path": "*.docx"}], "path is not used"),
    ([{"code": "FID001", "reason": "r", "match": {"tag": ["ins"]}}],
     "single values"),
    ("FID001:tag=ins", "must be a list"),
])
def test_invalid_expectations_are_tool_errors(base_docx, expect, message):
    result = tool("compare", {"source": BASE, "edited": BASE, "expect": expect})
    assert result["isError"] is True
    assert message in result["content"][0]["text"]
    assert "structuredContent" not in result


# ------------------------------------------------------------------ paths
@pytest.mark.parametrize("path,message", [
    ("https://example.com/agreement.docx", "is a URL"),
    ("file:///etc/hosts", "is a URL"),
    ("ftp://example.com/deck.pptx", "is a URL"),
    ("//fileserver/share/agreement.docx", "network path"),
    ("\\\\fileserver\\share\\agreement.docx", "network path"),
    ("corpus", "not a regular file"),
    ("corpus/no-such-file.docx", "file not found"),
    ("", "must be the path of a file"),
    (42, "must be the path of a file"),
])
def test_only_local_files_are_read(path, message):
    result = tool("check", {"path": path})
    assert result["isError"] is True
    assert message in result["content"][0]["text"]


def test_compare_checks_both_paths(base_docx):
    url = tool("compare", {"source": "https://example.com/a.docx",
                           "edited": BASE})
    assert url["isError"] and "source:" in url["content"][0]["text"]
    missing = tool("compare", {"edited": BASE})
    assert missing["isError"] and "needs source" in missing["content"][0]["text"]
    extra = tool("check", {"path": BASE, "against": BASE})
    assert extra["isError"] and "against" in extra["content"][0]["text"]
