# Try a DOCX workflow pilot

If your process generates or edits DOCX files before human review, we can spend
30 minutes checking one before/after pair together. The aim is to find a useful
defect or learn where the checker adds noise. You can run it locally and keep
the documents on your machine. The checker source is [MIT licensed](../LICENSE).

Start with one real editing operation: a paragraph replacement, table update,
template merge or agent edit. Keep the exact original and resulting file.
Write down the intended changes before reading the checker report, including
any deliberate acceptance or rejection of existing revisions.

## First result

For a quick trial, use the [browser demo](https://dmitry-kov.github.io/ooxml-integrity/).
Select the edited file and add its original for comparison. Python and fonts
download at startup; selected documents are processed in the tab. Record the
checker version from the footer and whether startup or file selection caused
any trouble. Copy only the report excerpts you choose to discuss.

For a repeatable local run, use Python 3.9+ in a fresh virtual environment.
Create one with `python -m venv .venv`. Activate it using
`source .venv/bin/activate` on macOS/Linux or `.venv\Scripts\activate.bat` in
Windows Command Prompt, then run:

```sh
python -m pip install "ooxml-integrity==0.4.1"
python -m ooxml_integrity --version
python -m ooxml_integrity check edited.docx --against original.docx --no-config --coverage
```

Replace the example filenames with your pair. Quote paths containing spaces.
The first run ignores discovered config files to make the initial result clear.
Record any policy or baseline separately when testing your normal workflow.
Installation needs network access; the installed checker runs without network
access or model calls.

If a machine-readable report would help, keep a local copy:

```sh
python -m ooxml_integrity check edited.docx --against original.docx --no-config --coverage --json > pilot-report.json
```

Exit `0` means no finding reaches the chosen failure threshold, not that the
document is guaranteed correct. Exit `1` means findings reach that threshold;
the report is still available. Exit `2` indicates a usage error. The default
threshold is `error`; `--fail-on warn` includes warnings. JSON and diagnostic
messages can contain filenames and text snippets, so review them before sharing.

## Review together

Use a 30-minute session as a starting point:

| Time | Action | Record |
| --- | --- | --- |
| 0-5 min | Describe the generator, version and intended edit | One scenario and the original/output pair kept locally |
| 5-10 min | Run the checker with the original | Version, time to first usable result, startup obstacles |
| 10-20 min | Inspect each actionable finding against the actual document | Confirmed defect, false alarm or unresolved finding, with rule code |
| 20-30 min | Choose a fix or a small CI trial | Concrete next action, setup time and a repeat-run owner |

A missed defect is useful evidence too: describe what disappeared or changed
and how you verified it. An accepted upstream fixture, one successful run, and
ongoing CI use are different outcomes. Record a no-finding run as such; it is
not a measured accuracy score.

The checker has [known limits](support-matrix.md). In particular, `FID001` can
report counts removed by legitimate accept/reject operations, and count-neutral
revision text loss or a removed footnote revision can be missed. The
[existing-revision evidence](../evidence/docx-revisions/README.md) records those
cases. Keep intended changes and independent document review alongside findings.

## Try it after generation in CI

Once the pair and findings make sense, add this step to an existing GitHub
Actions job after the step that produces the edited document:

```yaml
- name: Check generated DOCX against its original
  uses: Dmitry-Kov/ooxml-integrity@v0.4.1
  with:
    version: "0.4.1"
    files: "out/edited.docx"
    against: input/original.docx
    config: none
    fail-on: error
    json-report: pilot-report.json
```

The example expects those two paths to exist on the runner; adapt them to the
generation step. Use the matching original for each output. Run on a trial
branch first and inspect the job summary. This step fails on error findings.
CI logs and artifacts follow your repository's visibility and retention rules.
Uploading the JSON report is optional; this example does not upload it.

If a finding is expected, first verify the intended document behavior, then
use a scoped ignore with a reason or a reviewed baseline as described in
[configuration](configuration.md). Record fixed and suppressed findings
separately. A suppressed finding is not a confirmed fix.

## Share the result and check whether it lasts

[Open the feedback form](https://github.com/Dmitry-Kov/ooxml-integrity/issues/new?template=checker-feedback.yml)
with your generator/version, checker version, finding codes, intended edit,
expected/actual behavior and how you verified it. GitHub issues are public.
A text description is enough; a document attachment is optional. To discuss a
pilot, describe the workflow and say you would like to try a session. Scheduling
and any private exchange can be agreed separately in that conversation.

After the first useful run, agree whether to check back at 7 and 28 days. Record
whether the checker actually ran again, stayed in CI, was disabled, or remains
untested. Ask which manual review or incident it helped avoid, what was noisy,
and whether the result was worth the setup effort. Discuss ownership and budget
only if the participant wants to continue. Agree separately before publishing
their name, documents or a case study.
