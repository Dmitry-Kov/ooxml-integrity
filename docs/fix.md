# Repairing what has one answer: `fix`

Most findings cannot be repaired from the file. When an edit loses a comment's
anchor, a style or a tracked change, putting it back means guessing what was
there. That is the editor's job, and a checker that guessed would start
competing with the tools it measures. `ooxml-integrity fix` therefore makes
only repairs whose correct result is unique, and proves each one by checking
the copy again.

```sh
ooxml-integrity fix edited.docx -o repaired.docx
```

```
edited.docx -> repaired.docx: 1 finding(s) repaired, re-checked
  anchor-replies  CMT005  comment id=15 is orphaned - present in comments.xml but anchored to nothing - the reviewer's note is invisible in Word
    reply 15 by Benchmark Editor ("Schedule 1 now defines it.") anchored at the range of comment 2 by Reviewer A, after reply 3, in word/document.xml, in the order Word writes a thread; Word does not show a reply without an anchor, so the reply becomes visible
    word/document.xml  /w:document/w:body/w:p[4]/w:commentRangeStart[3]
      (absent) -> <w:commentRangeStart w:id="15"/>
    word/document.xml  /w:document/w:body/w:p[4]/w:commentRangeEnd[3]
      (absent) -> <w:commentRangeEnd w:id="15"/>
    word/document.xml  /w:document/w:body/w:p[4]/w:r[5]
      (absent) -> <w:r><w:rPr><w:rStyle w:val="CommentReference"/>...</w:rPr><w:commentReference w:id="15"/></w:r>
verified: 1 finding(s) gone (CMT005), none added; compare(input, output): FID002 INFO comment anchors: 4 -> 5 ...; FID002 INFO character style references: 7 -> 8 ...; word/document.xml edited, 20 other ZIP member(s) copied as stored
input  sha256 17493a82...
output sha256 9608c649...
```

`fix` takes one `.docx` and writes a repaired copy to `-o`. It never writes to
the input. `--against SOURCE` also proves the copy loses nothing relative to
the source that the input did not already lose. `--force` replaces an existing
output (never the input). `--json` prints the report as JSON.

## The three repairs

The first two are the only repairs that a survey of 3,437 findings in 3,399
files found to have a unique result and to occur in real edit outputs. The
survey's Word check found the third. They are listed with the finding each one
answers.

**anchor-replies (`CMT005`).** The finding is a reply that has no anchor.
- **What Word does.** In Word, a reply is a comment that `commentsExtended`
  links to a parent (`w15:paraIdParent`). Word gives the reply no position of
  its own: it writes the reply's range start, range end and reference at the
  parent's range.
- **The repair** writes the same markers in the same order:
  - the reply's start after the thread's last start;
  - its end and a reference run after the thread's last reference run;
  - the reference run's properties are copied from the parent's reference run.
- **Edit outputs.** Codex, OpenCode, docx-mcp and docxengine wrote such
  replies in the review-history benchmark. Word does not show them until they
  are anchored.

**renumber-revisions (`REV001`).** The finding is a revision id used by more
than one tracked change.
- **The repair:** the first use in document order keeps the id. Every later
  use gets a fresh id above every `w:id` in the package, so it reuses no
  comment or bookmark id either.
- **What is kept:** a paragraph-mark/content pair, which Word writes with one
  id and the checker does not report, is not renumbered.
- **Why the result is unique:** nothing in a package refers to a revision by
  its id, and Word and LibreOffice renumber revisions when they save.
- **Edit outputs.** adeu splits an insertion around its edit and leaves both
  halves with the old id. Tools that address revisions by id then reach only
  one half.

**content-type (`PKG010`).** The finding is a part the main document relates,
declared with another content type than its relationship type requires.
- **Why the result is unique:** the relationship type names one content type,
  the one Word writes for it. `PKG010` reads fifteen such types; the repair
  uses the same table.
- **The repair** replaces the value of the part's `Override` `ContentType` in
  `[Content_Types].xml` with that type, spelled as Word writes it. Only the
  value between the quotes changes; the rest of `[Content_Types].xml` keeps its
  bytes.
- **Only an `Override`.** A part that `[Content_Types].xml` types only through
  a `Default` extension entry is refused: changing the `Default` would retype
  every other part with that extension, and `fix` does not add an `Override`.
- **What Word does.** Word for Mac 16.113.4 refused all five Codex `K5-S1`
  outputs of the review-history benchmark as unreadable. Codex declared their
  `commentsExtended` part `application/vnd.ms-word.commentsExtended+xml`. With
  only that value corrected, Word opens the file
  ([Word check](../evidence/review-history-benchmark/word-check-content-type/README.md)).
  On the captures, `fix` makes this repair and anchor-replies together. From
  codex-2's capture it writes, byte for byte, the copy Word opened with the
  reply in its parent's thread.
- **Other relationship types** were not opened in Word with a wrong content
  type. The report says so when it repairs one.

## What it refuses, and why

A repair runs only when its preconditions hold. Otherwise the finding is
listed as not repaired, with the reason. Every other finding of `check` (and,
with `--against`, of the comparison with the source) is listed too, with why
`fix` leaves it.

| Case | Reason |
|---|---|
| a top-level comment with no anchor | nothing links it to a parent, and its anchor position is lost; the text it was attached to is usually gone too |
| a reply whose parent has no anchor, or more than one | the thread's range is lost |
| a reply to a reply | its range is not unique |
| a reply whose thread does not share one range start, or whose reference is not in a run directly inside a paragraph (for example inside a tracked insertion) | where Word puts the reply there has not been observed |
| a reply whose parent's reference run has tracked formatting, or a character style the package does not define | copying the run would add a revision or an `STY001` |
| a repeated revision id where two of the uses are a paragraph-mark/content pair | which use collides is not unique |
| a part typed only by a `Default` extension entry in `[Content_Types].xml` | changing the `Default` would retype every other part with that extension |
| a part named by more than one `Override`, or related by types that require different content types | which content type applies is not unique |
| the part to edit is not UTF-8, or the bytes of an element cannot be located | the part could not be edited in place |
| `[Content_Types].xml` compressed with a method other than stored or deflate | `fix` writes only those two methods |
| `STY001` | removing the reference and defining the style are both choices |
| `TXT001` | adding `xml:space="preserve"` changes the text LibreOffice displays |
| `CMT001`, `CMT002` | where the range ended or started is not in the file |
| every `FID` finding | a difference from the source; fix never restores lost content or changes what an edit did |
| any other finding | no repair is defined for it |

`fix` also refuses a package it cannot rewrite exactly, and writes nothing:
- a missing or unreadable file, or one over an archive budget;
- a Strict Open XML package;
- any part that is not well-formed XML;
- a package where a check did not complete (`INT001`);
- no single main document;
- ZIP64 members, or Unicode Path extra fields, which give a member a second
  name;
- a `.pptx` or any file that is not `.docx`.

## What it guarantees

1. **A copy, never in place.** The output must not be the input under any
   name, including a hard link, and must not exist unless `--force` is given.
   The copy is written to a temporary file next to the output and renamed into
   place only after it is verified. Nothing is left behind otherwise.
2. **Every change is listed.** For each repaired finding, the report gives
   every element added or changed: the part, its XPath in the copy, its line in
   the input, and old → new. The JSON report adds the input and output SHA-256
   and the checker version.
3. **Only the repair's bytes change.**
   - Within an edited part, the repair's bytes are inserted or replaced in
     place. The XML declaration, attribute order, entity spellings and
     whitespace stay as they were. Re-serialising with lxml instead would
     have changed other bytes in 951 of the 3,236 main document parts of the
     repository and the public corpora.
   - The edited part is parsed again and must equal the intended element
     tree.
   - Every other ZIP member is copied as stored: the same local header,
     compressed bytes and data descriptor, in the same order. The central
     directory keeps every name, compression method, timestamp and attribute.
   - The output is deterministic. Only the edited part is compressed again,
     so its bytes depend on the zlib version.
4. **The copy is re-checked before it is written.** It succeeds only if:
   - every repaired finding is gone from `check(output)`, and nothing else
     appears or disappears;
   - `compare(input, output)` reports only the declared count increases;
   - with `--against`, `compare(source, output)` gains nothing that
     `compare(source, input)` lacked, beyond those increases;
   - the ZIP comparison above holds;
   - the input did not change during the run.

   The declared increases are `FID002` INFO for what anchor-replies inserts
   into the main part: one comment anchor per reply, and one character style
   reference when the parent's reference run names a style.
   renumber-revisions and content-type declare nothing.
5. **No content is restored or invented.** No text, range, author, date or run
   property of existing content changes. A repaired reply becomes visible in
   Word; the report says so, because that is what the file already said it
   contained. content-type changes a declaration, not a part.

## Exit codes

`fix` keeps the CLI's `0` for success and `2` for usage errors, and is built so
that `0` always means a verified copy exists:

| Exit | Meaning | Output |
|---|---|---|
| `0` | at least one finding repaired, and the copy re-checked | written |
| `1` | no `CMT005`, `REV001` or `PKG010` finding, or every one refused; the report says which and why | none |
| `2` | usage error (missing input, not `.docx`, output exists without `--force`, output is the input, no output directory), or a package `fix` does not rewrite (see above) | none |
| `3` | a repair could not be proved by the re-check, or failed internally | none |

`1` matches `check`'s "the document has findings the run cannot clear".
`3` is new: a script that treats `1` as "nothing to do" must not mistake a
failed proof for it, and a failed proof is a defect in `fix` to report.

## JSON report

`fix --json` prints one object. It has no schema version yet: its fields can
change until a release documents them
([compatibility](compatibility.md#machine-readable-formats)).

```
version         checker version
status          repaired | nothing-to-repair | input-refused | verification-failed
reason          one sentence
input           {path, sha256}
output          {path, sha256} or null when nothing was written
against         {path, sha256} or null
repaired        [{repair, finding, detail, changes: [{part, element, where, line, old, new}]}]
not_repaired    [{code, severity, message, where?, part?, extra?, origin: check|against,
                  reason, repair?}]
verification    null, or {passed, failures, check: {removed, added},
                compare_input_output, against_added, zip: {changed, copied}}
```

`old` is null for an element the repair added. For content-type, `part` is
`[Content_Types].xml`, `element` is `Override`, `where` is its path such as
`/Types/Override[11]`, and `old` and `new` are its `ContentType` attribute. A
usage error prints a message on stderr and no JSON.

## Evidence

- **Corpus record.** [`evidence/fix-repairs`](../evidence/fix-repairs/README.md)
  runs `fix` on every DOCX in the repository with one of the three findings:
  51 files. 29 were repaired and passed the re-check, against their source
  where one is recorded; 5 of them also had their content type repaired. In the
  other 22, 23 comments were refused for the reasons above. Every output is
  deterministic, and the benchmark oracle's verdict did not change.
- **Word for Mac and LibreOffice.** Word for Mac 16.113.4 and LibreOffice
  25.8.4.2 were given the repaired copies of 18 files on 2026-10-10. 17 are in
  the repository, and `fix` writes 12 of those copies byte for byte. The other
  five are the Codex `K5-S1` copies, repaired by anchor-replies alone; `fix` now
  also corrects their content type (below). The details are summarised in the
  [evidence record](../evidence/fix-repairs/README.md#word-for-mac-and-libreoffice).
  - **anchor-replies:** every repaired copy Word opened (7 of 7) shows the
    reply in its parent's thread. None of the originals shows it.
  - **renumber-revisions:** Word shows the same revisions, and accepting or
    rejecting each one alone gives the same result as in the original (6 of 6
    pairs).
  - **content-type:** Word refused the five Codex `K5-S1` outputs, before
    and after anchor-replies alone, because of their `commentsExtended`
    content type. `fix` now repairs both. On codex-2 it writes the copy Word
    opened with the reply in its thread, byte for byte. On the other four, the
    `[Content_Types].xml` and comment markers it writes are that copy's; those
    four outputs were not opened in Word.

## Limits

- Three repairs only, and only for what `check` reports.
- content-type was checked in Word for `commentsExtended` only, with one wrong
  value. The other fourteen relationship types rest on the type Word writes,
  not on an observed refusal.
- Archive budgets are the defaults; `fix` reads no config file.
- Word was checked as Word for Mac 16.113.4 only. Word for Windows and Word on
  the web were not checked.
