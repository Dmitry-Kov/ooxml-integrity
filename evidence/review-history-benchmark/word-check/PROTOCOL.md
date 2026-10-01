# Word for Mac check of wave-1 damage classes — declared before opening

One representative output per damage class the oracle found, and one control,
opened in Word for Mac through its normal UI. Inputs are byte copies of frozen
captures; their hashes are listed below. Nothing is saved: each file is opened,
observed and closed without saving. Normal alerts stay on; no repair mode is
chosen in advance; no preference is changed. Record the Word version, every
prompt and the choice made, and what the document and the Review pane show.

| File | Capture | What to observe | Declared expectation |
| --- | --- | --- | --- |
| 1-docx-cli-bullets.docx | docx-cli-5/K1-S1-plain | the two bulleted items near the end ("Invoices are payable…", "Late payment…") | the marker shows the text `&#8226;` instead of a bullet |
| 2-docx-cli-attribution.docx | docx-cli-5/K4-S1-tracked | the inserted list item "The Supplier shall maintain …": author of `professional liability insurance` | shown as A. Counsel's insertion; `professional indemnity insurance` deleted by Benchmark Editor |
| 3-docx-cli-wrong-span.docx | docx-cli-5/K4-S2-tracked | clause 4 (Fees): what is deleted and inserted, by whom | ` The Client may` deleted by Benchmark Editor; `disputed sum` shown as Reviewer A's; `disputed amount.` unchanged |
| 4-docx-mcp-reply.docx | docx-mcp-3/K5-S2-comment | the thread on "Completion Date": is the reply `Schedule 1 now defines it.` shown | the reply has no anchor in the document; hypothesis: Word does not show it (the alternative, shown through `commentsExtended`, is recorded as observed) |
| 5-docxengine-reply.docx | docxengine-1/K5-S2-comment | the same thread and reply | as for file 4 |
| 6-control-anchored-reply.docx | reference-1/K5-S2-comment | the same thread and reply, anchored like Word's own replies | the reply is shown in the thread |
| 7-docxengine-malformed-comments.docx | docxengine-1/K5-S1-comment | any prompt on open; comments shown after any repair | Word reports unreadable content and offers repair; record what remains after it |

SHA-256 of the inputs:

```text
77c9a7eb61d3f917fac6def2499357756def474b68dfbbc2c703260a6599026d  1-docx-cli-bullets.docx
57d2addcbb051a2318992822e5afd22c474bf86cdcd8b01aeafd8a52a0239675  2-docx-cli-attribution.docx
f26664cf789bbb38bff104473147a402168d5e0f8edc56a0208db432f59d4593  3-docx-cli-wrong-span.docx
f909351d2d871656b650fb1e06826f0b695e8bebeb935d01368c031b39450f73  4-docx-mcp-reply.docx
01869cba76c924b920ce9cffce626f0e88b3ba690bd404e98dd5fad5d97bf6b4  5-docxengine-reply.docx
4f51e6bedbf246e7a056e4380371335aaf88c738abe659e2f2e8b5aa08d0eb8e  6-control-anchored-reply.docx
152e91012280e770b8abb9fdbb9c04a5a6ef2b63fe5af326b657fb9737c93590  7-docxengine-malformed-comments.docx
```

These are observations of one Word build, not proof of conformance; a missing
prompt does not show that nothing was normalised.
