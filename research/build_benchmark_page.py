#!/usr/bin/env python3
"""Write the public results page of the review-history benchmark.

    python research/build_benchmark_page.py          # writes demo/benchmark/index.html
    python research/build_benchmark_page.py --check  # fails if the page is out of date

Every number on the page is read from the committed evidence: the frozen
evaluation (evaluation.json) and the later expectations analysis
(expectations/results.json). The page is static HTML with an inline SVG chart
and a table holding the same numbers; Pages deploys it with the demo.
"""
from __future__ import annotations

import argparse
import collections
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence/review-history-benchmark"
PAGE = ROOT / "demo/benchmark/index.html"
REPO = "https://github.com/Dmitry-Kov/ooxml-integrity"
BLOB = f"{REPO}/blob/main/evidence/review-history-benchmark"

#: (adapter, label, note) in display order; groups are separated in the chart.
GROUPS = [
    ("Control", [("reference", "Reference control", "edits the XML the way Word records it")]),
    ("Document tools", [
        ("python-docx-runs", "python-docx 1.2, Run.text =", "the careful path"),
        ("python-docx-setter", "python-docx 1.2, Paragraph.text =", "the tutorial and MCP-wrapper path"),
        ("adeu", "adeu 3.0.6", "tracked changes only"),
        ("docx-cli", "docx-cli 0.26.0", ""),
        ("office-word-mcp", "Office-Word-MCP-Server 1.1.11", "archived"),
        ("docx-mcp", "docx-mcp 0.7.4", ""),
        ("docxengine", "docxengine 1.0.0", ""),
    ]),
    ("Coding agents", [
        ("claude-code", "Claude Code 2.1, Opus 5.5", "five captures"),
        ("codex", "Codex 0.160, gpt-6.1-sol", "five captures"),
        ("opencode-qwen", "OpenCode, Qwen3.8 27B (local)", "one capture"),
    ]),
]
SEGMENTS = [("passed", "Done and preserved", "var(--s-done)"),
            ("undone", "Preserved, not done as asked", "var(--s-undone)"),
            ("damaged", "Damaged", "var(--s-damaged)")]


def tally() -> dict:
    evaluation = json.loads((EVIDENCE / "evaluation.json").read_text(encoding="utf-8"))
    out = collections.defaultdict(collections.Counter)
    for r in evaluation["results"]:
        c = out[r["adapter"]]
        c[r["status"]] += 1
        if r["status"] != "ok":
            continue
        preserved, done = r["preservation"]["preserved"], bool(r.get("completed"))
        c["passed" if preserved and done else "undone" if preserved else "damaged"] += 1
        if not preserved and r["detection"]["outcome"] == "detected":
            c["caught"] += 1
    return out


def expectations() -> dict:
    data = json.loads((EVIDENCE / "expectations/results.json").read_text(encoding="utf-8"))
    total = collections.Counter()
    for modes in data["summary"].values():
        for mode, counts in modes.items():
            for outcome, n in counts.items():
                total[(mode, outcome)] += n
    return {
        "correct": total[("without", "clean")] + total[("without", "false alarm")],
        "flagged_without": total[("without", "false alarm")],
        "flagged_with": total[("with", "false alarm")],
        "damaged": total[("without", "detected")] + total[("without", "missed")],
        "caught_without": total[("without", "detected")],
        "caught_with": total[("with", "detected")],
    }


def chart(counts: dict) -> str:
    """A 100% stacked bar per tool over the attempts that ran, as HTML so the
    labels keep their size on a phone."""
    e = html.escape
    rows = []
    for group, members in GROUPS:
        rows.append(f'<div class="bar-group" role="presentation">{e(group)}</div>')
        for adapter, label, _ in members:
            c = counts[adapter]
            ran = c["ok"]
            segments = []
            for key, name, color in SEGMENTS:
                if c[key]:
                    tip = f"{label}: {c[key]} of {ran} {name.lower()} ({round(100 * c[key] / ran)}%)"
                    segments.append(f'<span class="seg" style="flex-grow: {c[key]}; background: {color}" '
                                    f'title="{e(tip)}"></span>')
            summary = ", ".join(f"{c[key]} {name.lower()}" for key, name, _ in SEGMENTS if c[key])
            rows.append(f'<div class="bar-row"><div class="bar-label">{e(label)}</div>'
                        f'<div class="bar" role="img" aria-label="{e(label)}: {e(summary)} of {ran}">'
                        + "".join(segments) + f'</div><div class="bar-n">n = {ran}</div></div>')
    return f'<div class="bars">{"".join(rows)}</div>'


def table(counts: dict) -> str:
    e = html.escape
    head = ("<tr><th>Tool</th><th>Ran</th><th>Unsupported</th><th>Rejected</th>"
            "<th>Done and preserved</th><th>Preserved, not done</th><th>Damaged</th>"
            "<th>Damaged and reported by 0.4.6</th></tr>")
    body = []
    for group, members in GROUPS:
        body.append(f'<tr class="grp-row"><th colspan="8">{e(group)}</th></tr>')
        for adapter, label, note in members:
            c = counts[adapter]
            name = e(label) + (f' <span class="note">{e(note)}</span>' if note else "")
            caught = f"{c['caught']} of {c['damaged']}" if c["damaged"] else "–"
            cells = [c["ok"], c["unsupported"], c["rejected"], c["passed"], c["undone"],
                     c["damaged"], caught]
            body.append(f"<tr><th>{name}</th>" + "".join(f"<td>{v}</td>" for v in cells) + "</tr>")
    return f'<table class="results"><thead>{head}</thead><tbody>{"".join(body)}</tbody></table>'


def page() -> str:
    counts = tally()
    x = expectations()
    cli = counts["docx-cli"]
    return TEMPLATE.format(
        chart=chart(counts), table=table(counts), blob=BLOB, repo=REPO,
        claude=f"{counts['claude-code']['passed']} of {counts['claude-code']['ok']}",
        codex=f"{counts['codex']['passed']} of {counts['codex']['ok']}",
        cli_damaged=f"{cli['damaged']} of {cli['ok']}",
        flagged=f"{x['flagged_without']} → {x['flagged_with']}", correct=x["correct"],
        flagged_without=x["flagged_without"], flagged_with=x["flagged_with"],
        caught_without=x["caught_without"], caught_with=x["caught_with"], damaged=x["damaged"],
        setter=f"{counts['python-docx-setter']['damaged']} of {counts['python-docx-setter']['ok']}",
    )


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="no-referrer">
  <meta name="description" content="Six document tools and three coding agents made 30 ordinary edits to two reviewed contracts. What survived, what broke in Word, and what a checker can see.">
  <meta property="og:title" content="What survives when a tool edits a reviewed Word document">
  <meta property="og:description" content="Six document tools and three coding agents, 30 edits to reviewed contracts, an independent oracle and a native Word for Mac check.">
  <meta property="og:type" content="article">
  <meta property="og:url" content="https://dmitry-kov.github.io/ooxml-integrity/benchmark/">
  <title>What survives when a tool edits a reviewed Word document — ooxml-integrity</title>
  <link rel="icon" href="data:,">
  <link rel="stylesheet" href="../style.css">
  <style>
    :root {{ --s-done: #2a78d6; --s-undone: #eda100; --s-damaged: #e34948; --grid: #e1e0d9; }}
    .kpis {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin: 32px 0 0; }}
    .kpi {{ background: var(--sheet); border: 1px solid var(--line); border-radius: 6px; padding: 16px 18px; }}
    .kpi .label {{ font-size: 14px; color: var(--muted); margin: 0 0 6px; }}
    .kpi .value {{ font-size: 30px; font-weight: 600; letter-spacing: -.02em; line-height: 1.1; margin: 0; }}
    .kpi .foot {{ font-size: 13px; color: var(--muted); margin: 8px 0 0; }}
    .chart {{ background: var(--sheet); border: 1px solid var(--line); border-radius: 6px; padding: 18px 20px 12px; margin: 0; }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 8px 22px; margin: 0 0 10px; font-size: 14px; color: var(--ink); padding: 0; list-style: none; }}
    .legend li {{ display: flex; align-items: center; gap: 8px; }}
    .legend .sw {{ width: 12px; height: 12px; border-radius: 3px; display: inline-block; }}
    .bar-group {{ font-weight: 600; color: var(--muted); font-size: 12px; letter-spacing: .04em; text-transform: uppercase; margin: 14px 0 4px; }}
    .bar-group:first-child {{ margin-top: 4px; }}
    .bar-row {{ display: grid; grid-template-columns: 270px minmax(0, 1fr) 64px; align-items: center; gap: 4px 12px; padding: 5px 0; }}
    .bar-label {{ font-size: 14px; text-align: right; }}
    .bar {{ display: flex; gap: 2px; height: 18px; }}
    .seg {{ display: block; min-width: 2px; }}
    .seg:last-child {{ border-radius: 0 4px 4px 0; }}
    .bar-n {{ font-size: 13px; color: var(--muted); font-variant-numeric: tabular-nums; }}
    details.data {{ margin: 14px 0 0; }}
    details.data summary {{ cursor: pointer; color: var(--green); font-size: 14px; }}
    .scroll {{ overflow-x: auto; }}
    table.results {{ border-collapse: collapse; width: 100%; font-size: 14px; margin: 12px 0 0; }}
    table.results th, table.results td {{ border-bottom: 1px solid var(--line); padding: 7px 10px; text-align: right; font-variant-numeric: tabular-nums; }}
    table.results th:first-child {{ text-align: left; font-weight: 500; }}
    table.results thead th {{ font-weight: 600; font-size: 13px; color: var(--muted); vertical-align: bottom; }}
    table.results tr.grp-row th {{ text-align: left; font-size: 12px; letter-spacing: .04em; text-transform: uppercase; color: var(--muted); padding-top: 16px; }}
    .note {{ color: var(--muted); font-size: 12.5px; margin-left: 6px; }}
    .findings {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }}
    .finding {{ background: var(--sheet); border: 1px solid var(--line); border-radius: 6px; padding: 16px 18px; }}
    .finding h3 {{ margin: 0 0 6px; }}
    .finding p {{ margin: 0; font-size: 15px; }}
    .finding .who {{ color: var(--muted); font-size: 13.5px; margin: 8px 0 0; }}
    .prose {{ max-width: 760px; }}
    .visually-hidden {{ position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }}
    .prose p, .prose li {{ font-size: 16px; }}
    footer {{ border-top: 1px solid var(--line); margin: 64px 0 0; padding: 20px 0 40px; color: var(--muted); font-size: 14px; }}
    @media (max-width: 820px) {{
      main {{ padding: 0 16px; }}
      .kpis, .findings {{ grid-template-columns: 1fr; }}
      .bar-row {{ grid-template-columns: minmax(0, 1fr) 56px; }}
      .bar-label {{ grid-column: 1 / -1; text-align: left; }}
      nav {{ gap: 14px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div class="brand"><span class="mark" aria-hidden="true">[✓]</span> ooxml-integrity</div>
      <nav aria-label="Links">
        <a href="../">Demo</a>
        <a href="{blob}/README.md">Evidence</a>
        <a href="{repo}">GitHub</a>
      </nav>
    </header>

    <section class="hero" aria-labelledby="title">
      <h1 id="title">What survives when a tool edits a reviewed Word document</h1>
      <p class="lede">Two contract drafts with a live review history: comments and replies, other reviewers' pending tracked changes, footnotes and a header. Thirty ordinary requests: replace a phrase, reply to a comment, accept one revision, fix a footnote. Six document tools, python-docx on two code paths, and three coding agents ran them; an oracle that knows nothing about the checker compared every output with its source, and one output per kind of damage was opened in Word for Mac.</p>
      <div class="kpis">
        <div class="kpi"><p class="label">Claude Code, done and preserved</p><p class="value">{claude}</p><p class="foot">attempts, five captures</p></div>
        <div class="kpi"><p class="label">Codex, done and preserved</p><p class="value">{codex}</p><p class="foot">but some replies Word does not show</p></div>
        <div class="kpi"><p class="label">docx-cli outputs damaged</p><p class="value">{cli_damaged}</p><p class="foot">attempts that ran</p></div>
        <div class="kpi"><p class="label">Correct edits the checker flags</p><p class="value">{flagged}</p><p class="foot">of {correct}, once the requested change is declared (next release)</p></div>
      </div>
    </section>

    <section aria-labelledby="results">
      <div class="section-head">
        <h2 id="results">What each tool did</h2>
        <p>Share of the attempts that ran. <em>Done</em> means the requested text is in place and recorded as asked, tracked or not. <em>Preserved</em> means nothing else changed: comments, anchors, threads, other authors' revisions with their author and date, notes, lists, tables. Operations a tool has no interface for are left out; the table has them.</p>
      </div>
      <figure class="chart">
        <figcaption class="visually-hidden">Outcome of each attempt that ran, per tool</figcaption>
        <ul class="legend">
          <li><span class="sw" style="background: var(--s-done)"></span>Done and preserved</li>
          <li><span class="sw" style="background: var(--s-undone)"></span>Preserved, not done as asked</li>
          <li><span class="sw" style="background: var(--s-damaged)"></span>Damaged</li>
        </ul>
        {chart}
        <details class="data">
          <summary>Table with every count</summary>
          <div class="scroll">{table}</div>
        </details>
      </figure>
    </section>

    <section aria-labelledby="broke">
      <div class="section-head">
        <h2 id="broke">What broke, as Word shows it</h2>
        <p>Each class below was found by the oracle and then opened in Word for Mac 16.113.2. Where a tool's maintainers can fix it, an issue is filed.</p>
      </div>
      <div class="findings">
        <div class="finding"><h3>Bullets turn into <code>&amp;#8226;</code></h3><p>Any write escapes the list's existing bullet reference a second time; Word prints the literal text instead of a bullet.</p><p class="who">docx-cli, every output of the first document · <a href="https://github.com/kklimuk/docx-cli/issues/12">issue</a></p></div>
        <div class="finding"><h3>New words credited to another reviewer</h3><p>A tracked replacement inside another author's pending insertion leaves the new words without a wrapper of their own, so Word shows them as that author's; next to a nested deletion it also deletes the wrong words.</p><p class="who">docx-cli · <a href="https://github.com/kklimuk/docx-cli/issues/13">issue</a></p></div>
        <div class="finding"><h3>Replies nobody can see</h3><p>The reply is in the comments part and linked to its thread, but has no anchor in the document. Word shows the reply neither in the margin nor in the Reviewing pane.</p><p class="who">docx-mcp, docxengine, and the agents Codex and OpenCode · issues for <a href="https://github.com/SecurityRonin/docx-mcp/issues/21">docx-mcp</a> and <a href="https://github.com/ruwadgroup/docxengine/issues/2">docxengine</a></p></div>
        <div class="finding"><h3>A comments part Word has to repair</h3><p>A new comment uses a namespace prefix the part never declares. Word reports unreadable content; after repair the new comment is empty and has no author.</p><p class="who">docxengine, on a classic comments part · <a href="https://github.com/ruwadgroup/docxengine/issues/1">issue</a></p></div>
        <div class="finding"><h3>The title edited instead of the header</h3><p>Asked to change the header, the tool replaced the same words in the document title, which it could reach, and left the header alone.</p><p class="who">Office-Word-MCP-Server, docxengine</p></div>
        <div class="finding"><h3>Comment anchors and footnote references gone</h3><p>Setting a paragraph's or cell's text rebuilds its runs and drops the comment range and the footnote reference inside it; the note stays in its part and disappears from the page.</p><p class="who">python-docx <code>Paragraph.text =</code> / <code>_Cell.text =</code>: {setter} outputs</p></div>
        <div class="finding"><h3>Another reviewer's change accepted silently</h3><p>Editing inside a pending insertion, the agent removed the insertion's wrapper, so the other reviewer's proposed sentence now reads as agreed text.</p><p class="who">OpenCode with a local Qwen3.8 27B, 1 of 30</p></div>
      </div>
    </section>

    <section aria-labelledby="checker">
      <div class="section-head">
        <h2 id="checker">What a checker can see</h2>
      </div>
      <div class="prose">
        <p><a href="{repo}">ooxml-integrity</a> 0.4.6, the published version the protocol froze, compares an edited file with its source. It reported every comment anchor and footnote reference python-docx lost and the malformed comments part, and missed what it did not model: the escaped bullets, the misattributed words, the title edited instead of the header. 0.4.7 adds warnings for the first two.</p>
        <p>Most of its findings on correct edits were the requested change itself: accepting a revision lowers the revision count, an untracked header edit changes the header. The next release, already on the main branch, lets a caller <a href="{repo}/blob/main/docs/configuration.md#changes-the-edit-was-asked-to-make">declare such a change</a>: a matching finding is then expected, and an expectation nothing matches is an error, because the requested change did not happen. With expectations taken from each task's declaration, flagged correct outputs fell from {flagged_without} to {flagged_with} of {correct}, each of those left a true report outside the oracle's scope, and caught damaged outputs rose from {caught_without} to {caught_with} of {damaged}: the title edited instead of the header now shows. <a href="{blob}/expectations/README.md">Analysis</a>.</p>
      </div>
    </section>

    <section aria-labelledby="method">
      <div class="section-head">
        <h2 id="method">How it was run</h2>
      </div>
      <div class="prose">
        <ul>
          <li>The <a href="{blob}/PROTOCOL.md">protocol</a> and its 30 task declarations were frozen, with their hashes, before the first capture; later changes are dated amendments, made before the captures they affect.</li>
          <li>The first source is a synthetic contract; the second is a review record written by Word for Mac: two reviewers' comments, a threaded reply and tracked changes, including a deletion inside another reviewer's insertion.</li>
          <li>Each third-party document tool ran in its own container with no network, python-docx in the development environment. Each agent ran in a container whose only route out led to its model, with web tools off and no retries. Document tools were captured twice, agents five times, OpenCode once.</li>
          <li>The oracle reads both files into review facts and never imports the checker; a reference control that edits the XML the way Word does passes all 60 attempts.</li>
          <li>All captures, transcripts, receipts and the evaluation are in the <a href="{blob}/README.md">evidence folder</a>.</li>
        </ul>
        <p>Limits: two documents, one version of each tool and model, and counts of attempts rather than independent documents. Only one output per kind of damage was opened, in one build of Word for Mac.</p>
      </div>
    </section>

    <footer>
      ooxml-integrity is MIT-licensed research software. <a href="../">Try the checker in your browser</a> · <a href="{repo}">source</a> · <a href="{blob}/README.md">benchmark evidence</a>.
    </footer>
  </main>
</body>
</html>
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the page is out of date")
    args = parser.parse_args(argv)
    text = page()
    if args.check:
        current = PAGE.read_text(encoding="utf-8") if PAGE.exists() else ""
        if current != text:
            print(f"{PAGE.relative_to(ROOT)} is out of date; run research/build_benchmark_page.py",
                  file=sys.stderr)
            return 1
        return 0
    PAGE.parent.mkdir(parents=True, exist_ok=True)
    PAGE.write_text(text, encoding="utf-8")
    print(f"wrote {PAGE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
