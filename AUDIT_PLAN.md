# Audit and implementation plan

- Status: working plan, 2026-09-03
- Current source version: `0.3.1`
- Recommended next release: `0.4.0` (the baseline v2 change is intentionally
  breaking)

This document turns the current audit into an ordered implementation and
validation plan. The [support matrix](docs/support-matrix.md) remains the
authority for what the checker claims to support today.

## Executive conclusion

`ooxml-integrity` is a strong research-alpha and a credible foundation for a
trustworthy beta. It already has a useful product wedge:

> Catch silent damage in machine-edited Word and PowerPoint files before the
> files ship.

The strongest differentiator is not generic OOXML schema validation. It is the
combination of source-aware DOCX fidelity checks, deterministic package checks,
and offline PPTX layout preflight. The best initial users are teams that
generate or edit high-stakes Office files in automated pipelines: legaltech,
contract automation, regulated reporting, and internal AI/document platforms.
DOCX integrity and fidelity are the primary product wedge; PPTX layout is the
second product track and should expand only with renderer evidence.

The project is not ready to claim complete Office-file validation. The main
remaining risks are narrow real-world evidence, release-contract validation,
and several known PPTX model gaps.

## Audit snapshot

### What is already strong

- The product promise is narrow, understandable, and tied to real failure
  modes rather than generic document quality.
- The checker is deterministic, local, and does not require document upload,
  rendering, a model call, or a network service.
- DOCX self-consistency and source fidelity are separate concepts in the code
  and CLI. This is the correct architecture: a self-consistent file may still
  have silently lost content.
- Findings have stable rule codes, severities, JSON output, SARIF output,
  configuration, justified suppressions, and counted baselines.
- The repository contains reproducible fixtures, mutation research, renderer
  measurements, real agent outputs, and cross-platform CI.
- The code is small and modular enough to audit: package inspection, fidelity,
  policy, CLI, SARIF, font resolution, PPTX layout, and PPTX findings have clear
  boundaries.

### Hardening completed in the current working tree

These items are implemented and tested locally, but are not released merely by
being checked here:

- [x] Safe XML parsing with DTD, entity expansion, external access, recovery,
      and huge-tree mode disabled; `DOCTYPE` is rejected explicitly.
- [x] Package-wide DOCX relationship target checks, including the root
      `officeDocument` relationship and relationships owned by headers,
      footers, and other XML parts.
- [x] Graceful findings for directories, permission failures, and package I/O
      errors instead of uncaught tracebacks.
- [x] Fail-closed `--against`: an unreadable source or unsupported PPTX source
      comparison produces an error saying comparison was not performed.
- [x] Baseline format v2, with distinct identities for different fidelity
      losses and no plaintext document body stored in the baseline.
- [x] Composite GitHub Action installs the checker from its selected Action ref
      by default and no longer interpolates Action inputs into shell source.
- [x] A detailed support matrix distinguishes Supported, Partial, and Not
      checked surfaces.
- [x] Configurable archive budgets and package-part-name validation fail before
      member decompression with explicit findings.
- [x] Per-file coverage and `doctor` expose checked, estimated, skipped, and
      recognised unsupported capability instead of implying complete coverage.
- [x] Local verification: 232 passed, 7 environment-dependent font tests
      skipped; wheel and sdist built; the installed wheel checked the reference
      DOCX cleanly; YAML and Action shell syntax parsed successfully.

### Principal gaps and risks

| Priority | Risk | Why it matters | Required outcome |
| --- | --- | --- | --- |
| P0 | Narrow evidence corpus | One synthetic source and a small set of agent outputs cannot establish production precision. | Build a labelled, producer-diverse corpus and publish rule-level precision evidence. |
| P0 | Release-contract risk | Baseline v2 is breaking and JSON/rule lifecycle guarantees are not formally versioned. | Publish migration notes and define compatibility rules before the next release. |
| P1 | PPTX long-token false negative | A token wider than a wrapped box may not emit horizontal overflow. | Report the defect with calibrated confidence and regression fixtures. |
| P1 | TTC/OTC face selection | The indexed collection face may not be the face used for metrics. | Preserve and test the intended collection face index end to end. |
| P1 | PPTX geometry scope | Groups, rotations, tables, SmartArt, master-only objects, and presentation slide order are incomplete or unsupported. | Add features only with fixtures and renderer evidence; otherwise surface them as unsupported. |
| P1 | Font portability | Results depend on installed or metric-compatible fonts, which complicates first-run CI. | Add a `doctor` report and a documented reproducible font setup or supported font bundle strategy. |
| P2 | Operational maturity | Security reporting, contribution guidance, release automation, and provenance are incomplete. | Add project policies and a repeatable, reviewable release process. |

## Product boundary

### Positioning

Use this category and message consistently:

> Office artifact preflight for AI and document-automation pipelines.

The tool should answer four explicit questions:

1. Can the package be read safely enough to inspect?
2. Is the supported package and document structure internally consistent?
3. Did a machine edit lose supported content relative to its source?
4. For supported presentation shapes, is visible layout likely to break?

### Non-goals for the next two milestones

- Do not implement the full ECMA-376 schema set. The
  [Microsoft Open XML SDK](https://learn.microsoft.com/en-us/office/open-xml/word/how-to-validate-a-word-processing-document)
  and specialised validators such as
  [openxml-audit](https://github.com/BramAlkema/openxml-audit) already address
  schema conformance; they can be complementary tools.
- Do not add XLSX until the DOCX wedge has external production evidence. XLSX
  would multiply the rule surface before the current promise is validated.
- Do not market the checker as a malware scanner, semantic fact checker,
  accessibility auditor, or renderer-equivalent visual diff.
- Do not require customers to upload confidential documents. Any future hosted
  control plane should receive findings and metadata by default while checks
  continue to run locally or in the customer's infrastructure.
- Do not add a rule without evidence, a false-positive test, a severity
  rationale, and an explicit support boundary.

## Implementation priorities

### P0 — trustworthy beta

#### P0.1 Release the current hardening as `0.4.0`

Deliverables:

- Review the current diff and confirm the baseline v2 migration language.
- Bump the package version only when the release candidate is accepted.
- Run the complete Linux, macOS, and Windows CI matrix.
- Build and inspect wheel and sdist from a clean checkout.
- Exercise the composite Action from a pinned tag, including clean, findings,
  usage-error, baseline, JSON, and SARIF paths.
- Publish release notes that call out the breaking baseline migration.

Exit criteria:

- [ ] All supported Python/OS jobs pass from a clean checkout.
- [ ] The Action uses the code from the selected tag without an override.
- [ ] A v1 baseline fails with a clear regeneration instruction.
- [ ] A regenerated v2 baseline behaves consistently on all CI platforms.
- [ ] The release artifacts contain the expected package modules and metadata.
- [ ] No unexplained warning, skipped check, or undocumented compatibility
      change remains in the release candidate.

#### P0.2 Add archive resource limits

Deliverables:

- Configurable defaults for maximum entry count, total expanded bytes,
  per-entry expanded bytes, and suspicious compression ratio.
- Duplicate normalized part-name and traversal-like part-name detection.
- Limits enforced before reading all entries into memory.
- Clear package findings that distinguish invalid input from an internal error.
- Unit tests and fuzz/property tests for boundary values and adversarial ZIPs.

Exit criteria:

- [x] A document over any configured budget fails predictably without an
      unbounded allocation.
- [x] Normal corpus files remain byte-for-byte untouched and produce the same
      findings.
- [x] Limits and configuration keys are documented in the support matrix.
- [x] Peak memory and elapsed time are measured for representative large files.

#### P0.3 Add per-file coverage reporting

Recommended interface:

- `ooxml-integrity check ... --coverage` adds a machine-readable coverage block
  and a concise human summary.
- `ooxml-integrity doctor` reports environment capability: usable fonts,
  confidence class, parser/runtime versions, and unavailable checks.

The coverage model should distinguish:

- `checked`: a supported rule evaluated the surface;
- `not-present`: the supported surface was absent;
- `estimated`: a result exists with reduced confidence, for example a font
  substitution;
- `skipped`: a check could not run and explains why;
- `unsupported`: the file contains a recognised construct outside the model.

Exit criteria:

- [x] A user cannot receive an unqualified clean result when a requested check
      failed to run.
- [x] JSON gives stable coverage identifiers and reasons.
- [x] Human output stays concise by default and can show full detail on demand.
- [x] Grouped PPTX shapes, tables/SmartArt, missing font metrics, and unsupported
      source comparison are represented explicitly.

#### P0.4 Extend DOCX fidelity to headers and footers

Deliverables:

- Resolve source and edited header/footer parts through section relationships,
  not through matching filenames.
- Compare normalised story text and the supported tracked constructs as
  multisets, accounting for legitimate part renumbering and reuse.
- Distinguish deletion of a referenced story from a legitimate relationship or
  part rename.
- Add fixtures for first/even/default headers and footers, shared parts,
  multiple sections, empty stories, renumbering, and actual content loss.

Exit criteria:

- [x] Removing header or footer text from an existing source produces an error.
- [x] Renumbering an otherwise identical header/footer part stays clean.
- [x] Adding a new section or story does not become a false loss.
- [x] Six existing clean agent outputs remain clean.
- [x] The support matrix names the exact covered story types and limitations.

#### P0.5 Build the evidence corpus

Minimum beta corpus:

- At least 30 distinct source documents and 100 labelled source/output pairs.
- Multiple producers: Word for Windows, Word for Mac, Word Online,
  LibreOffice, `python-docx`, and at least one commercial or internal generator
  where available.
- Contracts, reports, letters, tables, multi-section documents, review-heavy
  documents, and documents with real headers/footers.
- Both clean edits and seeded defects; every expected finding is labelled.
- Sanitised or synthetic equivalents for anything that cannot be committed.

Progress recorded 2026-09-05:

- [x] A committed synthetic tranche contains 30 distinct sources and 120
      labelled pairs: 60 clean controls and 60 seeded defects.
- [x] Ten sources each were produced or opened-and-saved by `python-docx`,
      LibreOffice, and Word for Mac; six requested document classes are evenly
      represented.
- [x] Exact labels, hashes, provenance, sanitisation, producer versions, and
      per-rule TP/FP/FN are machine-readable and regression-gated.
- [ ] Add Word for Windows and Word Online sources, plus a source from an
      independent commercial/internal generator.
- [ ] Add privacy-reviewed real documents or defensible synthetic equivalents,
      and independently review their labels.

Exit criteria:

- [x] Error-level precision is at least 95% on the labelled synthetic tranche, with
      the denominator and labelling method published alongside the result.
- [x] Precision and recall are reported per rule, not only as one aggregate.
- [x] Every fixed false positive becomes a permanent regression test.
- [x] Corpus provenance, licences, sanitisation, and expected producer/renderer
      behaviour are recorded.

### P1 — evidence-backed capability expansion

Implement in this order:

1. Wrapped PPTX tokens wider than the usable text box.
2. Correct TTC/OTC face-index propagation into metric loading.
3. Presentation slide order through `p:sldIdLst`.
4. Master-specific theme resolution.
5. Group transforms and rotated bounds.
6. Table text and geometry.
7. SmartArt/chart text only after a reliable ownership and layout model exists.

Each item needs:

- a minimal OOXML fixture;
- at least one clean control and one true defect;
- evidence from the relevant Office renderer;
- a declared confidence level and severity rationale;
- a false-positive regression;
- support-matrix and rule-documentation updates.

Do not silently approximate a surface and call it Supported. If evidence is
insufficient, report Partial, Estimated, or Unsupported.

### P2 — operational and ecosystem maturity

- Add `SECURITY.md` with supported versions and a private disclosure route.
- Add `CONTRIBUTING.md` with fixture, evidence, and rule acceptance standards.
- Add automated release builds, artifact verification, provenance, and a
  release checklist.
- Define deprecation windows for rule codes, severity changes, config, JSON,
  SARIF, and baseline formats.
- Publish one page per rule: failure mode, impact, evidence, false-positive
  boundary, and remediation.
- Provide a minimal container or documented hermetic runner for reproducible
  CI font behaviour.
- Consider integrations only after the CLI contract is stable: pre-commit,
  GitLab CI, Azure Pipelines, and a PR Checks application.

## Rule acceptance checklist

A new or materially changed rule is ready only when all answers are yes:

- [ ] Is the invariant stated without relying on implementation details?
- [ ] Is there evidence that the condition causes user-visible or structural
      damage in a named producer or renderer?
- [ ] Are severity and confidence justified?
- [ ] Are clean, defective, boundary, and false-positive fixtures present?
- [ ] Does the rule fail closed if its prerequisites are unavailable?
- [ ] Does the finding identify a useful part, XPath, slide, or shape where
      possible?
- [ ] Does it include a safe remediation or diagnostic next step?
- [ ] Are JSON, SARIF, baseline identity, suppression, and path handling tested?
- [ ] Are time and memory costs bounded?
- [ ] Is the support matrix updated without broadening the claim beyond the
      evidence?

## Definitions of readiness

### `0.4.0` release-ready

- The current hardening diff is reviewed and the complete CI matrix is green.
- Baseline v2 migration is documented and tested end to end.
- Built artifacts and the pinned composite Action pass smoke tests.
- Known unsupported surfaces remain documented; no new completeness claim is
  introduced.

### Public beta-ready

- All P0 items are complete.
- There are no known open P0 correctness or security defects.
- Every Supported surface has clean, defective, boundary, and malformed-input
  coverage where malformed input is meaningful.
- Per-file coverage and environment confidence are visible to users.
- Archive resources are bounded and adversarial inputs are tested.
- The minimum beta corpus exists and meets the error-precision target.
- At least two external teams have run the checker in CI for four weeks.
- Installation to first useful local result takes under 10 minutes; CI
  integration takes under 30 minutes for a new user following the docs.
- More than half of actionable error findings in design-partner runs are fixed,
  not merely suppressed.

### `1.0` ready

- At least three external teams have used the checker in production for 6–8
  weeks, including one high-stakes DOCX workflow.
- Error-level precision remains at least 99% on the versioned labelled corpus
  and is reported by rule.
- Recall is at least 95% for the labelled defect classes the support matrix
  declares Supported; unsupported classes are not included in that claim.
- There are no known fail-open paths for a requested Supported check.
- Rule codes, config, JSON, SARIF, baseline format, and deprecation policy have
  explicit compatibility guarantees.
- Resource limits, fuzzing, malformed-input tests, and security reporting are
  operational.
- Windows and macOS Office evidence exists for the core DOCX promise; the PPTX
  promise includes PowerPoint editing and Slide Show evidence where relevant.
- Release artifacts are reproducible enough to inspect, have provenance, and
  pass installation tests before publishing.

## Commercial validation and monetisation

Keep the engine, CLI, core rules, JSON/SARIF formats, and public benchmark open.
The defensible asset is not secrecy around the MIT-licensed parser; it is the
labelled corpus, measured precision, policy history, integrations, enterprise
operations, and reputation for trustworthy findings.

Recommended order of monetisation:

1. **Pipeline audit / certification.** Review a customer's document automation
   pipeline, build a private regression corpus, add policies, and deliver a
   failure report. Pricing hypothesis: USD 2,000–10,000 per engagement.
2. **Team control plane with a local runner.** Central policies, finding history,
   trends, attestations, PR status, and fleet management; document bytes remain
   local by default. Pricing hypothesis: USD 99–299 per organisation per month.
3. **Enterprise deployment.** Self-hosted/VPC operation, SSO/RBAC, audit log,
   signed policy packs, SLA, private rules, and long-term support. Pricing
   hypothesis: USD 15,000–60,000 per year.
4. **OEM and expert support.** Embed the engine in document-generation products,
   maintain private rule packs, or certify new producer/renderer combinations.

These prices are hypotheses, not targets to encode in the product before
validation.

Commercial validation gates:

- [ ] Complete 12–15 interviews with legaltech, reporting, and internal
      document-platform teams.
- [ ] Run five concierge audits using customers' real source/output pairs.
- [ ] At least three of five design partners add the checker to CI.
- [ ] At least two pay for a pilot, renew, or sign a concrete letter of intent.
- [ ] Time to first useful finding meets the beta targets.
- [ ] More than half of reported error findings are fixed rather than
      suppressed.
- [ ] Design partners can name prevented document incidents or manual review
      work, and attach a monetary value or willingness to pay to that outcome.
- [ ] Customers identify central policy/history or self-hosted operation as a
      budget-worthy problem before a control plane is built.

If those gates fail, improve the rule set, onboarding, or target segment before
building a hosted product.

## Recommended sequence

1. Release the current hardening as `0.4.0` after review and full CI.
2. Grow the DOCX corpus with design partners and label source/output pairs.
3. Fix the two bounded PPTX correctness gaps: long tokens and TTC/OTC faces.
4. Measure beta precision and onboarding before expanding format scope.
5. Sell pipeline audits first; build a control plane only after repeated demand.

The guiding rule is simple: prefer a smaller Supported surface with measured
precision and explicit gaps over a broad validator that can return an
unqualified clean result after silently skipping the risky parts.
