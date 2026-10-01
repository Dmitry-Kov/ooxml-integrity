# Word for Mac check of wave-1 damage classes

**Seven files opened in Word for Mac 16.113.2 (build 26092012) on macOS 27.0,
2026-10-01. All five damage classes appear in Word as the oracle described them,
and the control reply shows where it should.** The [protocol](PROTOCOL.md), with the
expected result for each file and the input hashes, was committed at 13:43
(UTC+5), before the first file was opened at 13:47. Inputs are byte copies of
frozen captures. Their SHA-256 matched the protocol before and after the check.
Nothing was saved.

| File | Capture | Word shows | 0.4.6 checker | Expected |
| --- | --- | --- | --- | --- |
| 1 | docx-cli-5 / K1-S1-plain | both bullets of the last list read `&#8226;` instead of `•` | nothing | confirmed |
| 2 | docx-cli-5 / K4-S1-tracked | `professional liability insurance` as **A. Counsel**'s insertion; `professional indemnity insurance` deleted by Benchmark Editor | `FID002` INFO only | confirmed |
| 3 | docx-cli-5 / K4-S2-tracked | Benchmark Editor deleted ` The Client may`; `disputed sum` inside **Reviewer A**'s insertion; `disputed amount.` unchanged. Clause 4 reads `…valid invoice.disputed sum withhold disputed amount.` | `FID002` INFO only | confirmed |
| 4 | docx-mcp-3 / K5-S2-comment | the thread on `Completion Date` shows Reviewer A and Reviewer B only; the reply `Schedule 1 now defines it.` is in neither the margin nor the Reviewing pane | `CMT005` ERROR | confirmed |
| 5 | docxengine-1 / K5-S2-comment | as file 4 | `CMT005` ERROR | confirmed |
| 6 | reference-1 / K5-S2-comment (control) | the reply by Benchmark Editor in the `Completion Date` thread | clean | confirmed |
| 7 | docxengine-1 / K5-S1-comment | "Word found unreadable content…"; after **Yes**, Show Repairs lists `Comments 1`. The two original comments survive; the new one is an empty comment with no author on the first item of the last list | `XML001`, `CMT004`, `CMT006` ERROR | confirmed |

In the frozen evaluation, `CMT005` on files 4 and 5 counts as a false alarm: K5 was
already not completed, and the oracle found nothing lost. Word confirms the
finding is true, as the [results](../README.md) assumed. 0.4.6 reports nothing on files
1–3: it does not look for literal references in list labels, and the wrong
attribution shows only when one compares who owns which characters.

Screenshots, downscaled from the originals: [1](screens/1-bullets-all-markup.jpg),
[2](screens/2-attribution-all-markup.jpg), [3](screens/3-wrong-span-all-markup.jpg),
[4](screens/4-thread-focused.jpg), [5](screens/5-reply-all-markup.jpg),
[6](screens/6-control-reply-all-markup.jpg), 7: [prompt](screens/7-unreadable-warning.jpg),
[repairs](screens/7-show-repairs.jpg), [recovered](screens/7-recovered-all-markup.jpg).
[observations.json](observations.json) records each file's result, the prompts and
the choices made.

## How it was run

Each file was opened with File → Open, no repair mode chosen in advance, AutoSave
off, Review → All Markup with the Reviewing pane open. No revision was accepted or
rejected, and no file was saved. Every file was closed without saving. For file 7,
Word opened the recovered copy as `Document1`; on close the save was declined.
The operator was a computer-use agent on the maintainer's Mac. It recorded what
the window and the Reviewing pane showed, and its accessibility-tree dumps of
both back each observation.

The check was not blind: while looking for the files, the agent saw lines of the
protocol's expectations. Each result above rests on the screenshot and the
accessibility tree, not on that expectation. On every open, an installed Adobe
PDF add-in raised a Visual Basic "File not found" error twice. Both were
dismissed with **End**. The add-in is unrelated to the documents, and the error
appeared for all seven files alike.

## Limits

One build of Word for Mac, one representative output per damage class. A file
that opens without a prompt may still be normalised. The pane's revision and
comment counts (file 1: 5 / 2; 2: 6 / 2; 3: 16 / 3; 4 and 5: 16 / 4; 6: 17 / 5;
7 after recovery: 6 / 3) describe what Word displays, including the empty
recovered comment. Word for Windows and Word on the web were not checked.
