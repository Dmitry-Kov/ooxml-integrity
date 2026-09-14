#!/usr/bin/env python3
"""Fixed local-agent-v1 capture. No remote endpoints, feedback or script repairs."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from zipfile import BadZipFile
from lxml import etree as E

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research import docx_benchmark as bench

HOST = "http://127.0.0.1:11434"
MODEL = "qwen2.5-coder:7b"
SEEDS = (101, 102, 103)
OPTIONS = {"temperature": 0, "num_ctx": 8192, "num_predict": 4096}


def api(endpoint, payload=None, timeout=1200):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(HOST + endpoint, data=data,
                                     headers={"Content-Type": "application/json"})
    # Never inherit a proxy setting for these loopback-only calls.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout) as response:
        return json.load(response)


def messages(action):
    text = (bench.BASE / "AGENT.md").read_text()
    blocks = re.findall(r"```text\n(.*?)\n```", text, re.S)
    if len(blocks) != 3:
        raise ValueError("Frozen prompt inventory changed")
    return [{"role": "system", "content": blocks[0]},
            {"role": "user", "content": blocks[1 if action == "save" else 2]}]


def request_body(action, seed):
    return {"model": MODEL, "messages": messages(action), "stream": False,
            "think": False, "options": {**OPTIONS, "seed": seed}}


def extract_script(content):
    fenced = re.fullmatch(r"\s*```[^\n]*\n(.*?)\n```\s*", content, re.S)
    return (fenced.group(1) + "\n", "removed_one_outer_fence") if fenced else (content, "verbatim")


def python_details(python):
    code = ("import sys,json,importlib.metadata as m;print(json.dumps(dict("
            "version=sys.version,base_prefix=sys.base_prefix,executable=sys.executable,"
            "packages={n:m.version(n) for n in ['python-docx','lxml','typing_extensions']})))")
    return json.loads(subprocess.check_output([str(python), "-I", "-c", code], text=True))


def sandbox_profile(work, python, details):
    """macOS deny network/fork; writable cwd and read-only Python/system files.

    Exceptions belong inside require-not: a broad deny overrides separate allow
    rules in Seatbelt. No document, results or checker directory is readable.
    """
    work, venv, base = work.resolve(), python.absolute().parent.parent, Path(details["base_prefix"])
    quote = lambda p: json.dumps(str(p))
    roots = (work, venv, base, Path("/System"), Path("/usr/lib"), Path("/private/preboot"))
    allowed = " ".join("(subpath " + quote(p) + ")" for p in roots)
    # Directory traversal/listing is allowed only on ancestors, not their files.
    ancestors = set(work.parents) | set(venv.parents) | set(base.parents)
    ancestors |= {Path("/dev/null"), Path("/dev/urandom")}
    allowed += " " + " ".join("(literal " + quote(p) + ")" for p in sorted(ancestors))
    return "\n".join([
        "(version 1)", "(allow default)", "(deny network*)", "(deny process-fork)",
        "(deny file-read-data (require-not (require-any " + allowed + ")))",
        "(deny file-write* (require-not (require-any (subpath " + quote(work)
        + ') (literal "/dev/null"))))',
    ]) + "\n"


def execute(python, work, profile):
    command = ["/usr/bin/sandbox-exec", "-f", str(profile), str(python), "-I", "-B", "edit.py"]
    environment = {"PATH": str(python.parent), "LANG": "en_US.UTF-8", "TMPDIR": str(work)}
    started = time.monotonic()
    try:
        result = subprocess.run(command, cwd=work, env=environment, capture_output=True,
                                timeout=60)
        record = {"returncode": result.returncode, "timeout": False}
        stdout, stderr = result.stdout, result.stderr
    except subprocess.TimeoutExpired as exc:
        record = {"returncode": None, "timeout": True}
        stdout, stderr = exc.stdout or b"", exc.stderr or b""
    (work / "stdout.txt").write_bytes(stdout)
    (work / "stderr.txt").write_bytes(stderr)
    return {**record, "command": command, "environment": environment,
            "duration_seconds": time.monotonic() - started}


def model_record():
    entries = [m for m in api("/api/tags")["models"] if m["name"] == MODEL]
    if len(entries) != 1:
        raise ValueError("Declared local model is not installed")
    return {"tag": entries[0], "show": api("/api/show", {"model": MODEL}),
            "runtime": api("/api/version")}


def prepare(python, directory, runtime_receipt):
    bench.frozen_protocol()
    details = python_details(python)
    if not details["version"].startswith("3.12.") or details["packages"]["python-docx"] != "1.2.0" or details["packages"]["lxml"] != "6.1.3":
        raise ValueError("Wrong declared Python environment")
    directory.mkdir(parents=True, exist_ok=False)
    model = model_record()
    declaration = {"schema": 1, "pipeline": "local-agent-v1", "declared_at": bench.utc(),
                   "protocol_sha256": bench.digest(bench.PROTOCOL), "harness_sha256": bench.digest(__file__),
                   "evaluator_sha256": bench.digest(bench.__file__), "python": str(python),
                   "python_details": details, "model": model,
                   "runtime_installation": json.loads(runtime_receipt.read_text()),
                   "requests": {f"{action}-{seed}": request_body(action, seed)
                                for action in ("save", "edit") for seed in SEEDS},
                   "cases": [{"id": f"{name}-{action}-{seed}", "profile": name,
                              "action": action, "seed": seed, **source}
                             for name, source in bench.frozen_protocol()["sources"].items()
                             for action in ("save", "edit") for seed in SEEDS],
                   "rules": {"script_timeout_seconds": 60, "model_timeout_seconds": 1200,
                             "script_repairs": 0, "model_retries": 0, "checker_feedback": False}}
    bench.save_json(directory / "declaration.json", declaration)
    (directory / "capture-harness.py").write_bytes(Path(__file__).read_bytes())
    return declaration


def capture(directory, work_root):
    declaration = json.loads((directory / "declaration.json").read_text())
    if declaration["harness_sha256"] != bench.digest(__file__):
        raise ValueError("Agent capture harness drift")
    if declaration["protocol_sha256"] != bench.digest(bench.PROTOCOL):
        raise ValueError("Protocol drift")
    current = model_record()
    if current != declaration["model"]:
        raise ValueError("Runtime/model declaration drift")
    python = Path(declaration["python"])
    if python_details(python) != declaration["python_details"]:
        raise ValueError("Python environment drift")
    work_root.mkdir(parents=True, exist_ok=False)
    receipt = {"schema": 1, "pipeline": "local-agent-v1", "started_at": bench.utc(),
               "declaration_sha256": bench.digest(directory / "declaration.json"),
               "command": [sys.executable, *sys.argv], "cases": []}
    bench.save_json(directory / "started.json", receipt)
    for case in declaration["cases"]:
        work = work_root / case["id"]
        work.mkdir()
        artifacts = directory / case["id"]
        artifacts.mkdir()
        source = ROOT / case["path"]
        if bench.digest(source) != case["sha256"]:
            raise ValueError("Source drift")
        shutil.copyfile(source, work / "input.docx")
        profile = artifacts / "sandbox.sb"
        profile.write_text(sandbox_profile(work, python, declaration["python_details"]))
        request = declaration["requests"][f"{case['action']}-{case['seed']}"]
        bench.save_json(artifacts / "request.json", request)
        record = {**case, "started_at": bench.utc(), "status": "error"}
        start = time.monotonic()
        try:
            response = api("/api/chat", request)
            bench.save_json(artifacts / "response.json", response)
            record["model_duration_seconds"] = time.monotonic() - start
            content = response["message"]["content"]
            (artifacts / "response.txt").write_text(content)
            script, record["extraction"] = extract_script(content)
            (work / "edit.py").write_text(script)
            record["execution"] = execute(python, work, profile)
            output = work / "output.docx"
            record["status"] = "ok" if (record["execution"]["returncode"] == 0 and output.is_file() and not output.is_symlink()) else "error"
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
        for path in sorted(work.iterdir()):
            if path.is_file() and not path.is_symlink():
                shutil.copyfile(path, artifacts / path.name)
        record["input_unchanged"] = bench.digest(work / "input.docx") == case["sha256"] if (work / "input.docx").is_file() else False
        record["artifacts_sha256"] = {p.name: bench.digest(p) for p in sorted(artifacts.iterdir()) if p.is_file()}
        record["finished_at"] = bench.utc()
        bench.save_json(artifacts / "attempt.json", record)
        receipt["cases"].append(record)
        print(case["id"], record["status"], flush=True)
    receipt["finished_at"] = bench.utc()
    bench.save_json(directory / "capture.json", receipt)
    return receipt


def evaluate(directory):
    declaration = json.loads((directory / "declaration.json").read_text())
    receipt = json.loads((directory / "capture.json").read_text())
    if receipt["declaration_sha256"] != bench.digest(directory / "declaration.json"):
        raise ValueError("Declaration drift")
    if declaration["evaluator_sha256"] != bench.digest(bench.__file__):
        raise ValueError("Independent evaluator drift")
    if {c["id"] for c in receipt["cases"]} != {c["id"] for c in declaration["cases"]} or len(receipt["cases"]) != 30:
        raise ValueError("Incomplete agent attempt inventory")
    results = []
    for case in receipt["cases"]:
        artifacts = directory / case["id"]
        for name, digest in case["artifacts_sha256"].items():
            if bench.digest(artifacts / name) != digest:
                raise ValueError("Artifact drift")
        result = {"id": case["id"], "status": case["status"], "action": case["action"],
                  "requested_change_completed": None, "protected_content_preserved": None,
                  "checker_detection": "not_evaluated", "overall_success": False}
        output = artifacts / "output.docx"
        if output.is_file():
            try:
                result.update(bench.inspect_pair(ROOT / case["path"], output, case["action"], "local-agent-v1"))
                result["overall_success"] = bool(case["status"] == "ok" and case["input_unchanged"]
                                                 and result["requested_change_completed"] and result["protected_content_preserved"])
            except (ValueError, KeyError, BadZipFile, E.XMLSyntaxError) as exc:
                result["evaluation_error"] = f"{type(exc).__name__}: {exc}"
        results.append(result)
    return {"pipeline": "local-agent-v1", "capture_sha256": bench.digest(directory / "capture.json"),
            "evaluator_sha256": bench.digest(bench.__file__), "cases": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--python", type=Path, required=True)
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument("--runtime-receipt", type=Path, required=True)
    p = sub.add_parser("capture")
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument("--work-root", type=Path, required=True)
    for name in ("evaluate", "verify"):
        p = sub.add_parser(name)
        p.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    args.directory = args.directory.absolute()
    if args.command == "prepare":
        prepare(args.python.absolute(), args.directory, args.runtime_receipt)
    elif args.command == "capture":
        capture(args.directory, args.work_root.absolute())
    else:
        result = evaluate(args.directory)
        path = args.directory / "evaluation.json"
        if args.command == "evaluate":
            bench.save_json(path, result)
        elif json.loads(path.read_text()) != result:
            raise ValueError("Agent evaluation drift")
        print(json.dumps({"attempts": len(result["cases"]), "successes": sum(c["overall_success"] for c in result["cases"])}))


if __name__ == "__main__":
    main()
