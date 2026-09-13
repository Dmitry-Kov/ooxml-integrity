#!/usr/bin/env python3
"""One local model response/execution per frozen boundary task, no repair."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from zipfile import BadZipFile
from lxml import etree as E

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research import capture_docx_agent as a
from research import docx_benchmark as b
from research import docx_boundaries as n

DIGEST = "dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364"


def prepare(python, directory, installation):
    data = n.protocol()
    model = a.model_record()
    if model["tag"]["digest"] != DIGEST or model["runtime"]["version"] != "0.30.7":
        raise ValueError("Declared model/runtime unavailable")
    details = a.python_details(python)
    if not details["version"].startswith("3.12.14") or details["packages"] != {
            "python-docx": "1.2.0", "lxml": "6.1.3", "typing_extensions": "4.16.0"}:
        raise ValueError("Python environment drift")
    prompts = json.loads((n.BASE / "prompts.json").read_text())
    requests = {f"{task}-{seed}": {"model": a.MODEL, "stream": False, "think": False,
                "options": {**a.OPTIONS, "seed": seed},
                "messages": [{"role": "system", "content": prompts["system"]},
                             {"role": "user", "content": prompts[task]}]}
                for task in n.TASKS for seed in a.SEEDS}
    declaration = {"adapter": "local-agent-boundaries-v1", "declared_at": b.utc(),
                   "protocol_sha256": b.digest(n.PROTOCOL), "harness_sha256": b.digest(__file__),
                   "evaluator_sha256": b.digest(n.__file__), "model": model, "python": str(python),
                   "python_details": details, "runtime_installation": json.loads(installation.read_text()),
                   "requests": requests, "command": [sys.executable, *sys.argv],
                   "rules": {"script_timeout": 60, "model_timeout": 1200, "script_repairs": 0,
                             "model_retries": 0, "checker_feedback": False},
                   "cases": [{"id": f"{p}-{task}-{seed}", "profile": p, "task": task, "seed": seed,
                              "path": source["path"], "sha256": source["sha256"]}
                             for p, source in data["sources"].items() for task in n.TASKS for seed in a.SEEDS]}
    directory.mkdir(parents=True, exist_ok=False)
    b.save_json(directory / "declaration.json", declaration)
    (directory / "capture-harness.py").write_bytes(Path(__file__).read_bytes())


def capture(directory, work_root):
    n.protocol()
    d = json.loads((directory / "declaration.json").read_text())
    if d["harness_sha256"] != b.digest(__file__) or d["protocol_sha256"] != b.digest(n.PROTOCOL):
        raise ValueError("Declaration drift")
    if a.model_record() != d["model"] or a.python_details(Path(d["python"])) != d["python_details"]:
        raise ValueError("Runtime/model drift")
    work_root.mkdir(parents=True, exist_ok=False)
    receipt = {"adapter": d["adapter"], "started_at": b.utc(), "command": [sys.executable, *sys.argv],
               "declaration_sha256": b.digest(directory / "declaration.json"), "cases": []}
    b.save_json(directory / "started.json", receipt)
    for case in d["cases"]:
        work, artifacts = work_root / case["id"], directory / case["id"]
        work.mkdir()
        artifacts.mkdir()
        source = ROOT / case["path"]
        if b.digest(source) != case["sha256"]:
            raise ValueError("Source drift")
        shutil.copyfile(source, work / "input.docx")
        profile = artifacts / "sandbox.sb"
        profile.write_text(a.sandbox_profile(work, Path(d["python"]), d["python_details"]))
        request = d["requests"][f"{case['task']}-{case['seed']}"]
        b.save_json(artifacts / "request.json", request)
        record = {**case, "started_at": b.utc(), "status": "error"}
        started = time.monotonic()
        try:
            response = a.api("/api/chat", request)
            b.save_json(artifacts / "response.json", response)
            record["model_duration_seconds"] = time.monotonic() - started
            content = response["message"]["content"]
            (artifacts / "response.txt").write_text(content)
            script, record["extraction"] = a.extract_script(content)
            (work / "edit.py").write_text(script)
            record["execution"] = a.execute(Path(d["python"]), work, profile)
            output = work / "output.docx"
            if record["execution"]["returncode"] == 0 and output.is_file() and not output.is_symlink():
                record["status"] = "ok"
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
        for path in sorted(work.iterdir()):
            if path.is_file() and not path.is_symlink():
                shutil.copyfile(path, artifacts / path.name)
        record["input_unchanged"] = (work / "input.docx").is_file() and b.digest(work / "input.docx") == case["sha256"]
        record["artifacts_sha256"] = {p.name: b.digest(p) for p in sorted(artifacts.iterdir()) if p.is_file()}
        record["finished_at"] = b.utc()
        b.save_json(artifacts / "attempt.json", record)
        receipt["cases"].append(record)
        print(case["id"], record["status"], flush=True)
    receipt["finished_at"] = b.utc()
    b.save_json(directory / "capture.json", receipt)


def evaluate(directory):
    data = n.protocol()
    d = json.loads((directory / "declaration.json").read_text())
    receipt = json.loads((directory / "capture.json").read_text())
    if (d["protocol_sha256"] != b.digest(n.PROTOCOL) or d["evaluator_sha256"] != b.digest(n.__file__)
            or d["harness_sha256"] != b.digest(directory / "capture-harness.py")
            or receipt["declaration_sha256"] != b.digest(directory / "declaration.json")):
        raise ValueError("Declaration drift")
    declared = {c["id"]: c for c in d["cases"]}
    expected = {f"{p}-{t}-{s}" for p in data["sources"] for t in n.TASKS for s in a.SEEDS}
    if set(declared) != expected or len(receipt["cases"]) != 60 or {c["id"] for c in receipt["cases"]} != expected:
        raise ValueError("Inventory drift")
    results = []
    for c in receipt["cases"]:
        artifacts = directory / c["id"]
        if any(c.get(k) != v for k, v in declared[c["id"]].items()) or c != json.loads((artifacts / "attempt.json").read_text()):
            raise ValueError("Attempt drift")
        if b.digest(ROOT / c["path"]) != c["sha256"]:
            raise ValueError("Input drift")
        if json.loads((artifacts / "request.json").read_text()) != d["requests"][f"{c['task']}-{c['seed']}"]:
            raise ValueError("Request drift")
        for name, digest in c["artifacts_sha256"].items():
            if b.digest(artifacts / name) != digest:
                raise ValueError("Artifact drift")
        result = {k: c[k] for k in ("id", "task", "profile", "seed", "status")}
        result.update(requested_change_completed=None, protected_content_preserved=None,
                      checker_detection="not_evaluated", overall_success=False)
        if (artifacts / "output.docx").is_file():
            try:
                result.update(n.inspect(ROOT / c["path"], artifacts / "output.docx", c["task"], d["adapter"]))
                result["overall_success"] = bool(c["status"] == "ok" and c["input_unchanged"] and result["requested_change_completed"] and result["protected_content_preserved"])
            except (ValueError, KeyError, IndexError, BadZipFile, E.XMLSyntaxError) as exc:
                result["evaluation_error"] = f"{type(exc).__name__}: {exc}"
        results.append(result)
    return {"adapter": d["adapter"], "capture_sha256": b.digest(directory / "capture.json"),
            "evaluation_harness_sha256": b.digest(__file__), "evaluator_sha256": b.digest(n.__file__),
            "checker_source_sha256": data["checker_source_sha256"], "cases": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--python", type=Path, required=True)
    p.add_argument("--runtime-receipt", type=Path, required=True)
    for name in ("capture", "evaluate", "verify"):
        p = sub.add_parser(name)
        if name == "capture":
            p.add_argument("--work-root", type=Path, required=True)
    for p in sub.choices.values():
        p.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    args.directory = args.directory.absolute()
    if args.command == "prepare":
        prepare(args.python.absolute(), args.directory, args.runtime_receipt)
    elif args.command == "capture":
        capture(args.directory, args.work_root.absolute())
    else:
        result = evaluate(args.directory)
        if args.command == "evaluate":
            b.save_json(args.directory / "evaluation.json", result)
        elif result != json.loads((args.directory / "evaluation.json").read_text()):
            raise ValueError("Evaluation drift")
        print(json.dumps({"attempts": len(result["cases"]), "successes": sum(c["overall_success"] for c in result["cases"])}))


if __name__ == "__main__":
    main()
