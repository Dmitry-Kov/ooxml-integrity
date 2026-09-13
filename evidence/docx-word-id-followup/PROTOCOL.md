# Word for Mac follow-up to BND-001 — declared before opening inputs

Question: does local Word display a repair/error prompt or lose review content
when opening and saving the actual adeu split-format output with two deletion
fragments sharing one ID? Does an otherwise identical unique-ID control behave
differently? This is a focused native-application observation, not a new editor
ranking and not a retrospective change to the boundary benchmark.

Inputs (each copied; the benchmark originals stay immutable):
1. source-control: unchanged basic derived benchmark source.
2. adeu-shared-id: exact basic-split output from adeu-1, two w:del ID 104 fragments.
3. unique-id-control: synthetic diagnostic derived from #2 by changing only the
   second deletion ID 104 to 106. All other XML nodes/attributes and package
   parts are the same. This is NOT a captured editor fix or a new adeu run.

Observe Word version/build and pre-existing open documents first. Open each local
copy through Word's normal UI, with normal alerts enabled. Do not use a repair
mode, dismiss a corruption prompt silently, accept/reject revisions, edit text,
or alter global Word preferences. Record each blocking prompt. If Word offers
repair, retain the prompt and either stop that case or explicitly label a separate
repair action before continuing. Do not touch unrelated user documents.

For an ordinary open, observe revision/comment display, save a new local DOCX
under outputs with Save As, close only this document, then reopen the saved output
and observe again. Keep outputs unmodified. Record normal prompts, app errors,
AX state observations and screenshots when available. A successful open is not
proof of conformance or absence of silent normalization. UI screenshots are
observations, not pixel-equivalence tests. No document goes to an external service.

Analyze raw XML after capture: all old/new revision payloads, authors, dates,
IDs and wrapper fragmentation; current/original text; comment body/anchors,
footnote body/reference and the target's direct bold/italic formatting. Reuse
existing XML facts/oracle. Word may renumber IDs, coalesce adjacent revision
fragments and normalize unrelated formatting/metadata, so report those differences
explicitly; do not retrofit the frozen benchmark's strict profile to allow them.
Use the existing declared Word save comparison where applicable, and retain its
residual differences. Compare shared-ID and unique-ID results separately from the
source control. Checker output is a separate observation, never the oracle.

Consult primary ECMA/Microsoft sources for annotation-ID semantics, distinguish
normative requirements from observed Word tolerance. Do not modify checker rules,
benchmarks, original labels or scores during this follow-up. Do not send messages,
file issues, publish or push. Retain commands/hashes and exact UI reproduction
steps. Report any blocked step and limitations rather than claiming it ran.
