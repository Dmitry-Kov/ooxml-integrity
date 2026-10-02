#!/usr/bin/env python3
"""Wave 2 of the review-history benchmark: coding agents.

Each attempt gives one agent a fresh directory holding only the task's source
as `input.docx` and the task's prompt, wrapped in `PROMPT`. The agent runs in
its own container on the internal network `ooxml-bench-agents`, which has no
route out; the egress container (research/review_history_agents_egress.py) is
its only way to its model: CONNECT tunnels to `ALLOWED` hosts on port 443, and
a relay to the host's Ollama. Containers run as user 65534 with every
capability dropped, no new privileges and memory and process limits.

The agent's stdout (its JSON event stream) and stderr, its exit code, the
egress log lines for its address and the scripts it left in the directory are
kept next to the capture; `output.docx`, if the agent wrote one, is the
attempt's output. Status: `timeout` after `TIMEOUT` seconds; `ok` when
`output.docx` is a ZIP package; otherwise `rejected` when the agent exited 0
(it finished without an output) and `error` when it did not.

Credentials stay out of the repository and out of the record: Claude Code reads
CLAUDE_CODE_OAUTH_TOKEN from tmp/agents/claude.env; Codex uses the ChatGPT
login made for these containers in tmp/agents/codex-auth/auth.json, copied into
each attempt's CODEX_HOME and copied back when Codex refreshes it.

    python research/review_history_agents.py egress      # start network + egress
    python research/review_history_agents.py smoke AGENT DOCX PROMPT
"""
from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "tmp" / "agents"
NETWORK = "ooxml-bench-agents"
EGRESS = "ooxml-bench-egress"
EGRESS_IMAGE = ("python:3.12-slim@sha256:"
                "f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f")
ALLOWED = ["api.anthropic.com", "chatgpt.com", "auth.openai.com"]
TIMEOUT = 3600
PROMPT = ("You are working in the current directory, which contains the Word document "
          "input.docx. {prompt} Write the result to output.docx in the current directory "
          "and leave input.docx unchanged. Python 3 with python-docx and lxml is installed; "
          "nothing else can be installed and there is no internet access.")
LIMITS = ["--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", "65534:65534",
          "--memory", "4g", "--pids-limit", "512", "--network", NETWORK]
PROXY = ["-e", "HTTPS_PROXY=http://egress:3128", "-e", "https_proxy=http://egress:3128",
         "-e", "NO_PROXY=", "-e", "no_proxy="]
#: scripts and notes the agent leaves behind, kept for reading its approach
KEPT_SUFFIXES = {".py", ".sh", ".js", ".ts", ".txt", ".md", ".json", ".xml", ".log"}
KEPT_LIMIT = 256 * 1024

OPENCODE_CONFIG = {
    "$schema": "https://opencode.ai/config.json",
    "model": "ollama/qwen3.8-64k",
    "share": "disabled",
    "autoupdate": False,
    "permission": {"edit": "allow", "bash": "allow", "webfetch": "deny"},
    "provider": {"ollama": {
        "npm": "@ai-sdk/openai-compatible", "name": "Ollama",
        "options": {"baseURL": "http://ollama.internal:11434/v1"},
        "models": {"qwen3.8-64k": {"name": "qwen3.8-64k", "tool_call": True, "reasoning": True,
                                   "limit": {"context": 65536, "output": 16384}}}}},
}

AGENTS = {
    "claude-code": {
        "image": "ooxml-bench-agent-claude:2.1.287",
        "command": lambda prompt: ["claude", "-p", prompt, "--model", "claude-opus-5-5",
                                   "--output-format", "stream-json", "--verbose",
                                   "--dangerously-skip-permissions",
                                   "--disallowedTools", "WebSearch,WebFetch"],
        "env": PROXY + ["-e", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1",
                        "-e", "DISABLE_AUTOUPDATER=1"],
        "secrets": "claude.env",
    },
    "codex": {
        "image": "ooxml-bench-agent-codex:0.160.0",
        "command": lambda prompt: ["codex", "exec", "--json", "--skip-git-repo-check",
                                   "--dangerously-bypass-approvals-and-sandbox", "-C", "/work",
                                   "-m", "gpt-6.1-sol", prompt],
        "env": PROXY + ["-e", "CODEX_HOME=/home/agent/.codex"],
        "codex_auth": "codex-auth/auth.json",
    },
    "opencode-qwen": {
        "image": "ooxml-bench-agent-opencode:1.18.34",
        "command": lambda prompt: ["opencode", "run", "--pure", "--format", "json", "--auto",
                                   "-m", "ollama/qwen3.8-64k", prompt],
        "env": ["-e", "OPENCODE_CONFIG=/home/agent/opencode.json"],
    },
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _docker(*args, check=True, timeout=120) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check,
                          timeout=timeout)


def _status(timed_out: bool, is_package: bool, exit_code) -> str:
    if timed_out:
        return "timeout"
    if is_package:
        return "ok"
    return "rejected" if exit_code == 0 else "error"


#: what each attempt must run on; preflight() refuses anything else
IMAGE_IDS = {
    "claude-code": "sha256:c46f9bfa7aa3332371a900412b91e747070e087b074ab03d694c26638ec9d336",
    "codex": "sha256:53aa9e4db22bc8599092945d00224c2266450b3dbcafb6f3f86cc9f617c62e14",
    "opencode-qwen": "sha256:f4bea522134d32616fbabf9da8594d360185bafcf68ac2e1610c3132541527d7",
}
OLLAMA_MODEL = ("qwen3.8-64k:latest",
                "c69cc4be857da78a56d0fe9791751c7f3f656989da5c2eca9e866aefe9b226fd")


def preflight(agent: str) -> None:
    image = _docker("image", "inspect", "-f", "{{.Id}}", AGENTS[agent]["image"]).stdout.strip()
    assert image == IMAGE_IDS[agent], (agent, image)
    if agent == "opencode-qwen":
        import urllib.request
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("http://127.0.0.1:11434/api/tags", timeout=30) as response:
            models = {m["name"]: m["digest"] for m in json.load(response)["models"]}
        assert models.get(OLLAMA_MODEL[0]) == OLLAMA_MODEL[1], models.get(OLLAMA_MODEL[0])
    if AGENTS[agent].get("secrets"):
        assert (STATE / AGENTS[agent]["secrets"]).stat().st_size > 0, "credentials missing"
    if AGENTS[agent].get("codex_auth"):
        assert (STATE / AGENTS[agent]["codex_auth"]).is_file(), "codex login missing"


def egress() -> None:
    """The internal network and the egress container, created if absent."""
    if _docker("network", "inspect", NETWORK, check=False).returncode:
        _docker("network", "create", "--internal", NETWORK)
    if _docker("container", "inspect", EGRESS, check=False).returncode == 0:
        return
    _docker("run", "-d", "--name", EGRESS, "--network", "bridge", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--user", "65534:65534",
            "-v", f"{ROOT / 'research' / 'review_history_agents_egress.py'}:/egress.py:ro",
            EGRESS_IMAGE, "python", "-u", "/egress.py", *ALLOWED)
    _docker("network", "connect", "--alias", "egress", "--alias", "ollama.internal", NETWORK,
            EGRESS)


def _egress_lines(address: str, since: str) -> list[dict]:
    logs = _docker("logs", "--since", since, EGRESS).stdout.splitlines()
    out = []
    for line in logs:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if record.get("client") == address:
            out.append(record)
    return out


def _home(agent: str, home: Path) -> None:
    """Per-attempt HOME: the agent's configuration, nothing from earlier attempts."""
    home.mkdir(parents=True)
    if agent == "opencode-qwen":
        (home / "opencode.json").write_text(json.dumps(OPENCODE_CONFIG, indent=1))
    if agent == "codex":
        codex = home / ".codex"
        codex.mkdir()
        shutil.copyfile(STATE / AGENTS[agent]["codex_auth"], codex / "auth.json")
        (codex / "config.toml").write_text('cli_auth_credentials_store = "file"\n')


def run(agent: str, source: Path, prompt: str, folder: Path, label: str) -> dict:
    """One attempt. Writes the record under `folder` and returns it."""
    spec = AGENTS[agent]
    attempt = STATE / "attempts" / f"{agent}-{label}-{time.time_ns()}"
    work, home = attempt / "work", attempt / "home"
    work.mkdir(parents=True)
    shutil.copyfile(source, work / "input.docx")
    _home(agent, home)
    for path in (attempt, work, home, *home.rglob("*")):
        path.chmod(0o777 if path.is_dir() else 0o666)
    name = f"ooxml-agent-{agent}-{label}".replace("_", "-")
    _docker("rm", "-f", name, check=False)
    command = ["run", "-d", "--name", name, *LIMITS, *spec["env"],
               "-e", "HOME=/home/agent", "-v", f"{home}:/home/agent", "-v", f"{work}:/work",
               "-w", "/work"]
    if spec.get("secrets"):
        command += ["--env-file", str(STATE / spec["secrets"])]
    command += [spec["image"], *spec["command"](PROMPT.format(prompt=prompt))]
    since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 1))
    began = time.monotonic()
    container = _docker(*command).stdout.strip()
    address = _docker("inspect", "-f",
                      "{{(index .NetworkSettings.Networks \"%s\").IPAddress}}" % NETWORK,
                      container).stdout.strip()
    timed_out = False
    try:
        exit_code = int(_docker("wait", container, timeout=TIMEOUT).stdout.strip() or -1)
    except subprocess.TimeoutExpired:
        timed_out, exit_code = True, None
        _docker("kill", container, check=False)
    seconds = round(time.monotonic() - began, 1)
    logs = subprocess.run(["docker", "logs", container], capture_output=True, timeout=120)
    image_id = _docker("inspect", "-f", "{{.Image}}", container).stdout.strip()
    _docker("rm", "-f", container, check=False)
    if agent == "codex":
        refreshed = home / ".codex" / "auth.json"
        store = STATE / spec["codex_auth"]
        if refreshed.exists() and refreshed.read_bytes() != store.read_bytes():
            shutil.copyfile(refreshed, store)

    folder.mkdir(parents=True, exist_ok=True)
    transcript = folder / f"{label}.jsonl.gz"
    transcript.write_bytes(gzip.compress(logs.stdout, mtime=0))
    stderr = logs.stderr.decode("utf-8", "replace")
    kept = {}
    for path in sorted(work.rglob("*")):
        if (path.is_file() and path.name not in ("input.docx", "output.docx")
                and path.suffix.lower() in KEPT_SUFFIXES and path.stat().st_size <= KEPT_LIMIT):
            target = folder / f"{label}.files" / path.relative_to(work)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            kept[str(path.relative_to(work))] = _sha(path)
    output = work / "output.docx"
    is_package = output.is_file() and zipfile.is_zipfile(output)
    status = _status(timed_out, is_package, exit_code)
    record = {
        "agent": agent, "image": spec["image"], "image_id": image_id, "status": status,
        "exit_code": exit_code, "seconds": seconds, "timeout_seconds": TIMEOUT,
        "input_unchanged": _sha(work / "input.docx") == _sha(source),
        "transcript": transcript.name, "transcript_sha256": _sha(transcript),
        "stderr_tail": stderr[-2000:], "files": kept,
        "other_files": sorted(str(p.relative_to(work)) for p in work.rglob("*")
                              if p.is_file() and str(p.relative_to(work)) not in kept
                              and p.name not in ("input.docx", "output.docx")),
        "egress": _egress_lines(address, since),
    }
    record["output"] = output if is_package else None
    return record


def adapter(agent: str):
    def perform(task: dict, editor: dict, output: Path) -> tuple[str, str]:
        preflight(agent)
        egress()
        record = run(agent, ROOT / task["source_path"], task["prompt"],
                     output.parent / "agent", task["id"])
        produced = record.pop("output")
        if produced is not None:
            shutil.copyfile(produced, output)
        return record["status"], json.dumps(record, ensure_ascii=False)
    return perform


AGENT_ADAPTERS = {name: adapter(name) for name in AGENTS}


def main(argv: list[str]) -> int:
    if argv[:1] == ["egress"]:
        egress()
        print("network and egress ready")
        return 0
    if argv[:1] == ["smoke"] and len(argv) == 4:
        egress()
        agent, docx, prompt = argv[1:]
        folder = STATE / "smoke" / agent
        record = run(agent, Path(docx).resolve(), prompt, folder, f"smoke-{int(time.time())}")
        produced = record.pop("output")
        if produced is not None:
            shutil.copyfile(produced, folder / f"output-{int(time.time())}.docx")
        print(json.dumps(record, indent=1, ensure_ascii=False))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
