"""Baseline v2 identities must not hide a different fidelity loss."""
from __future__ import annotations

import hashlib
import json

import pytest

from ooxml_integrity import ERROR, WARN, Finding
from ooxml_integrity.policy import (
    BASELINE_VERSION,
    ConfigError,
    apply_baseline,
    fingerprint,
    make_baseline,
    read_baseline,
)


def _count_loss(tag: str, *, before: int = 2, after: int = 1) -> Finding:
    return Finding(
        "FID001",
        ERROR,
        f"{tag}: {before} -> {after}",
        extra={"tag": tag, "before": before, "after": after},
    )


def _body_loss(body: str, *, code: str = "FID004") -> Finding:
    return Finding(
        code,
        ERROR,
        "a source body was lost",
        part="word/comments.xml",
        extra={"body": body, "author": "Reviewer", "lost": 1,
               "in_source": 1},
    )


def test_baseline_v2_distinguishes_constructs_with_the_same_fid001_code():
    old = _count_loss("commentReference")
    new = _count_loss("ins")
    baseline = make_baseline({"edited.docx": [old]})
    allowance = dict(baseline["findings"])

    kept, dropped = apply_baseline("edited.docx", [new], allowance)

    assert kept == [new]
    assert dropped == []
    assert fingerprint("edited.docx", old) != fingerprint("edited.docx", new)


@pytest.mark.parametrize("code", ["FID001", "FID002"])
def test_count_fingerprint_uses_tag_but_not_volatile_counts(code):
    before = Finding(
        code, ERROR, "old measurement",
        extra={"tag": "commentReference", "before": 2, "after": 1},
    )
    after = Finding(
        code, ERROR, "new measurement",
        extra={"tag": "commentReference", "before": 200, "after": 199},
    )

    assert fingerprint("edited.docx", before) == fingerprint("edited.docx", after)


def test_baseline_v2_distinguishes_lost_bodies_without_leaking_them():
    body_a = "Board approval required before the confidential acquisition."
    body_b = "Confirm the termination fee against the signed schedule."
    old = _body_loss(body_a)
    new = _body_loss(body_b)
    baseline = make_baseline({"edited.docx": [old]})
    allowance = dict(baseline["findings"])

    kept, dropped = apply_baseline("edited.docx", [new], allowance)

    assert kept == [new]
    assert dropped == []
    serialized = json.dumps(baseline)
    assert body_a not in serialized
    assert hashlib.sha256(body_a.encode()).hexdigest() in serialized


@pytest.mark.parametrize("code", ["FID004", "FID005", "FID006"])
def test_body_fingerprint_is_stable_across_message_and_metadata_changes(code):
    body = "The body identity remains the same."
    old = _body_loss(body, code=code)
    changed = Finding(
        code,
        ERROR,
        "measurement and wording changed",
        part=old.part,
        extra={"body": body, "author": "Another display name", "lost": 7,
               "in_source": 20},
    )

    assert fingerprint("edited.docx", old) == fingerprint("edited.docx", changed)


def test_story_body_fingerprint_includes_kind_and_variant_without_plaintext():
    body = "Confidential acquisition code name"
    header = Finding(
        "FID007", ERROR, "lost header",
        extra={"story_kind": "header", "variant": "default", "body": body},
    )
    footer = Finding(
        "FID007", ERROR, "lost footer",
        extra={"story_kind": "footer", "variant": "default", "body": body},
    )

    assert fingerprint("edited.docx", header) != fingerprint("edited.docx", footer)
    assert body not in fingerprint("edited.docx", header)
    assert hashlib.sha256(body.encode()).hexdigest() in fingerprint(
        "edited.docx", header,
    )


def test_story_construct_fingerprint_is_stable_across_counts():
    old = Finding(
        "FID008", ERROR, "one lost",
        extra={"story_kind": "header", "variant": "first", "tag": "ins",
               "before": 2, "after": 1},
    )
    changed = Finding(
        "FID008", ERROR, "many lost",
        extra={"story_kind": "header", "variant": "first", "tag": "ins",
               "before": 200, "after": 20},
    )

    assert fingerprint("edited.docx", old) == fingerprint("edited.docx", changed)


def test_make_baseline_writes_version_two():
    baseline = make_baseline({"edited.docx": [_count_loss("ins")]})
    assert baseline["version"] == BASELINE_VERSION == 2


@pytest.mark.parametrize('key,new_value', [
    ('author', 'Another confidential author'), ('date', '2026-10-02T10:00:00Z'),
    ('source_text_sha256', hashlib.sha256(b'another source').hexdigest()),
    ('additional_text', 'another confidential addition'),
])
def test_insertion_growth_acknowledgement_does_not_hide_a_different_warning(key, new_value):
    extra = {'author': 'Private reviewer', 'date': '2026-10-01T10:00:00Z',
             'source_text_sha256': hashlib.sha256(b'private source').hexdigest(),
             'additional_text': 'private new text', 'additional_characters': 16}
    old = Finding('FID011', WARN, 'old wording', part='word/document.xml', extra=extra)
    new = Finding('FID011', WARN, 'new wording', part=old.part,
                  extra={**extra, key: new_value})
    baseline = make_baseline({'edited.docx': [old]})
    kept, dropped = apply_baseline('edited.docx', [new], dict(baseline['findings']))
    assert kept == [new] and dropped == []
    encoded = json.dumps(baseline)
    assert extra['author'] not in encoded and extra['additional_text'] not in encoded
    same = Finding('FID011', ERROR, 'changed wording/severity', part=old.part, extra=extra)
    assert fingerprint('edited.docx', old) == fingerprint('edited.docx', same)


def test_version_one_baseline_is_rejected_with_regeneration_instruction(tmp_path):
    path = tmp_path / "v1.json"
    path.write_text(json.dumps({"version": 1, "findings": {}}), encoding="utf-8")

    with pytest.raises(ConfigError, match=r"version 1.*--write-baseline"):
        read_baseline(path)


@pytest.mark.parametrize("version", [3, 99, "2", None, True])
def test_unknown_or_malformed_baseline_versions_are_rejected(tmp_path, version):
    path = tmp_path / "unknown.json"
    path.write_text(
        json.dumps({"version": version, "findings": {}}),
        encoding="utf-8",
    )

    with pytest.raises(
            ConfigError,
            match=r"(?i)unsupported baseline version.*regenerate"):
        read_baseline(path)


def test_read_baseline_keeps_the_existing_dictionary_api(tmp_path):
    path = tmp_path / "v2.json"
    expected = {"edited.docx::PPT001::slide1/Title": 2}
    path.write_text(
        json.dumps({"version": BASELINE_VERSION, "findings": expected}),
        encoding="utf-8",
    )

    assert read_baseline(path) == expected
