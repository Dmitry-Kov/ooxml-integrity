"""The candidate-wheel harness must never modify or replace the public site."""
import hashlib
import json
from pathlib import Path
import runpy
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not (ROOT / "demo").is_dir(), reason="demo is not shipped in the sdist")


@pytest.fixture
def preview():
    return runpy.run_path(str(ROOT / "research/prepare_browser_preview.py"))["prepare_preview"]


@pytest.fixture
def wheel(tmp_path):
    path = tmp_path / "ooxml_integrity-0.4.1-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ooxml_integrity-0.4.1.dist-info/METADATA", "Name: ooxml-integrity\nVersion: 0.4.1\n")
    return path


def test_candidate_override_is_only_in_preview(preview, wheel, tmp_path):
    public = ROOT / "demo/worker.js"
    original = public.read_bytes()
    destination = tmp_path / "preview"
    receipt = preview(wheel, destination)
    assert public.read_bytes() == original
    worker = (destination / "worker.js").read_text()
    assert 'const CHECKER_VERSION = "0.4.1";' in worker
    assert 'new URL("_wheels/ooxml_integrity-0.4.1-py3-none-any.whl", import.meta.url).href' in worker
    assert (destination / "_wheels" / wheel.name).read_bytes() == wheel.read_bytes()
    assert receipt["sha256"] == hashlib.sha256(wheel.read_bytes()).hexdigest()
    assert json.loads((destination / "_preview.json").read_text()) == receipt
    # Rebuilding an owned preview removes old test-only assets.
    (destination / "stale.txt").write_text("stale")
    assert preview(wheel, destination) == receipt
    assert not (destination / "stale.txt").exists()


@pytest.mark.parametrize("destination", [ROOT, ROOT / "demo", ROOT / "demo/examples"])
def test_preview_cannot_overlap_public_site(preview, wheel, destination):
    with pytest.raises(ValueError, match="separate from the public demo"):
        preview(wheel, destination)


def test_preview_does_not_replace_unrelated_directory(preview, wheel, tmp_path):
    destination = tmp_path / "unrelated"
    destination.mkdir()
    sentinel = destination / "keep.txt"
    sentinel.write_text("keep me")
    with pytest.raises(ValueError, match="not a generated wheel preview"):
        preview(wheel, destination)
    assert sentinel.read_text() == "keep me"


def test_preview_rejects_other_package(preview, wheel, tmp_path):
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("other-1.dist-info/METADATA", "Name: other\nVersion: 1\n")
    with pytest.raises(ValueError, match="must contain ooxml-integrity"):
        preview(wheel, tmp_path / "preview")
    assert not (tmp_path / "preview").exists()
