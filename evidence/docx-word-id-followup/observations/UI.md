# Native Word observations

Captured on 2026-09-13 UTC using CUA native application UI. These are selected
AX lines transcribed from that session, plus operator observations; not a complete
raw UI transcript. Screenshots were inspected in the session but not exported.
Version/build and input/output hashes are in ../capture.json. No pre-existing
document was open. Word was left on its Home/New screen with no document open.

Each case used this sequence:

1. Cmd+O; local file picker; enter the absolute input path using its path field
   (typing `/` opens it); open the selected file. Inspect AX and screenshot.
2. Cmd+Shift+S; select this repository's outputs directory; set the output name;
   retain `Word Document (.docx)`; click Save. Inspect the saved window.
3. Cmd+W; Cmd+O; open the output using the local file picker. Inspect AX and
   screenshot again, then Cmd+W.

Only normal open/save file pickers appeared. No repair prompt was observed during
any of the three initial opens or three output reopens. No save warning appeared.
No repair, accept/reject, content edit, or global preference change was performed.
These observations do not exclude silent normalization by Word.

## source-control -> source-control-word

The source screenshot showed the original marker, existing deleted text,
comment and footnote. Selected saved/reopened AX lines:

```text
The cycle marker is **EDIT***BEFORE*. The service is renewable and optional.
text Reviewer B
text Deleted:
text entry area (disabled, settable)  retired
Description: Reviewer C Comment, Active, Value: Preserve this independent delivery comment.
Description: Footnote area, Value: The review record includes retained supporting information.
text Value: source-control-word Saved to my Mac
```

## adeu-shared-id -> adeu-shared-id-word

The initial, saved and reopened document had the same following selected AX
content. The path changed from inputs/adeu-shared-id.docx to
outputs/adeu-shared-id-word.docx; the final window reported Saved to my Mac.

```text
The cycle marker is **DONE***AFTER*. The service is renewable and optional.
text Evidence Editor
text Deleted:
Description: EDITBEFORE, Value: **EDIT***BEFORE*
text Reviewer B
text Deleted:
text entry area (disabled, settable)  retired
Description: Reviewer C Comment, Active, Value: Preserve this independent delivery comment.
Description: Footnote area, Value: The review record includes retained supporting information.
text Value: adeu-shared-id-word Saved to my Mac
```

## unique-id-control -> unique-id-control-word

The initial, saved and reopened document had the same marker, Evidence Editor
deletion, Reviewer B deletion, Reviewer C comment and footnote lines as the
shared-ID case above. The path changed from inputs/unique-id-control.docx to
outputs/unique-id-control-word.docx. The reopened title line was:

```text
text Value: unique-id-control-word Saved to my Mac
```

Bold/italic notation above is emitted by Word's AX representation. It is not a
pixel comparison or a full rendering/layout assessment. Exact direct formatting
and review metadata are evaluated separately from the package XML.
