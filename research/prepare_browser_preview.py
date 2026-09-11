"""Make a test-only demo copy that installs one local wheel. Never edits demo/."""
import argparse
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import re
import shutil
from urllib.parse import quote
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"
SPEC_LINE = 'const CHECKER_SPEC = `ooxml-integrity==${CHECKER_VERSION}`;'


def prepare_preview(wheel, destination):
    wheel, destination = Path(wheel).resolve(), Path(destination).resolve()
    if destination == DEMO or DEMO in destination.parents or destination in DEMO.parents:
        raise ValueError("Preview must be separate from the public demo and its parents")
    if not wheel.name.endswith("-py3-none-any.whl"):
        raise ValueError("Pyodide preview requires a pure Python py3-none-any wheel")
    with zipfile.ZipFile(wheel) as archive:
        metadata = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
        if len(metadata) != 1:
            raise ValueError("Expected exactly one wheel METADATA")
        headers = BytesParser().parsebytes(archive.read(metadata[0]))
    if re.sub(r"[-_.]+", "-", headers.get("Name", "")).lower() != "ooxml-integrity":
        raise ValueError("Preview wheel must contain ooxml-integrity")
    version = headers.get("Version")
    if not version:
        raise ValueError("Wheel metadata has no version")
    worker = (DEMO / "worker.js").read_text()
    version_pattern = r'^const CHECKER_VERSION = "[^"]+";$'
    if len(re.findall(version_pattern, worker, re.M)) != 1 or worker.count(SPEC_LINE) != 1:
        raise ValueError("Worker install declarations changed; review the preview adapter")
    worker = re.sub(version_pattern, lambda _: f"const CHECKER_VERSION = {json.dumps(version)};", worker, flags=re.M)
    worker = worker.replace(SPEC_LINE, f'const CHECKER_SPEC = new URL({json.dumps("_wheels/" + quote(wheel.name))}, import.meta.url).href;')
    receipt = {
        "kind": "local-wheel-preview", "version": version, "wheel": wheel.name,
        "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
    }
    # Refuse to replace an unrelated directory, including a tracked directory.
    if destination.exists():
        marker = destination / "_preview.json"
        if not marker.is_file() or json.loads(marker.read_text()).get("kind") != receipt["kind"]:
            raise ValueError("Destination exists and is not a generated wheel preview")
        if destination in wheel.parents:
            raise ValueError("Input wheel must be outside the preview being replaced")
        shutil.rmtree(destination)
    shutil.copytree(DEMO, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (destination / "worker.js").write_text(worker)
    (destination / "_wheels").mkdir()
    shutil.copy2(wheel, destination / "_wheels" / wheel.name)
    (destination / "_preview.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "tmp/browser-preview")
    args = parser.parse_args()
    print(json.dumps(prepare_preview(args.wheel, args.output), indent=2))
