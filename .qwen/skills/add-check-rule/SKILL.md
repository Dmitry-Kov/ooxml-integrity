---
name: add-check-rule
description: Add a new finding code (a new check) to ooxml-integrity, or change what an existing one reports. Use when asked to detect a new kind of defect in .docx or .pptx files, to add a rule such as CMT008 or FID017, or to change a rule's severity or scope.
---

# Add or change a check

A rule is a public interface: other projects gate their CI on its code and
severity. Work through every step; skipping the evidence or the documents is
how a rule ships that fails on clean files.

## 1. Decide before writing code

- **The defect.** One sentence: what is wrong in the file and what the reader
  sees in Word or PowerPoint because of it. If you cannot say what the reader
  sees, find out first, and say so if it was not opened in Office.
- **The code.** A new kind of check gets the next free number in its family
  (`grep -rn "CMT00" src docs/rules.md`). Never reuse a code or give an
  existing one a second meaning.
- **The severity.** ERROR when content or its audit trail is lost or hidden,
  WARN when only appearance changes or intent is ambiguous, INFO for a fact a
  caller may expect. Follow `docs/compatibility.md`.
- **Where it lives.** One file alone: `inspector.py` (DOCX), `pptx_checks.py`
  (decks). A loss relative to a source: `fidelity.py` or a module it calls.

## 2. Implement

- Read XML through `xmlutil.fromstring`; never parse package bytes directly.
- A text box is written twice (`mc:Choice` and `mc:Fallback`); count it once
  with `xmlutil.alternative_branch`.
- If the check cannot run, report that as an error. Do not return nothing.
- If findings of the code need a stable identity in a baseline, add a branch
  to `fingerprint()` in `policy.py`.
- For `--introduced`: a `FID*` finding is never set aside. For another code,
  decide whether the source can already have it, and add it to `UNCHECKED` in
  `introduced.py` if it means "this part was not checked".

## 3. Test

- A regression for the defect, and a clean control that must stay silent.
- The boundary cases that made you choose the rule's limits.
- Assert the code, severity and location, not a copied message.

## 4. Measure

Run the rule on files it was not written for, before documenting it:

- the repository's own corpus and evidence pairs (`pytest` covers these);
- the public corpora in `docs/real-world-corpora.md`, if they are available on
  this machine. A finding on a file compared with itself is a false positive.

Record the run under a new `evidence/<name>/` directory: a `README.md` with the
command, date, versions, counts and a "Limits" section, and a `results.json`.
If the corpora are not available, say so in the report; do not invent counts.

## 5. Document

- `docs/rules.md`: the code, the version it arrives in, severity and scope.
- `docs/support-matrix.md`: what is and is not checked.
- `docs/compatibility.md`: when the rule can fail a gate that passed before.
- `CHANGELOG.md` and the release notes are written at release time; list what
  they will need to say in your report.

## 6. Finish

Run the `verify-change` skill. In the report, state what the rule does not
catch and which producers (Word, LibreOffice, python-docx) it was run against.
