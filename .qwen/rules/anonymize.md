---
description: anonymize.py is security-critical; a leak is worse than a refusal
paths:
  - 'src/ooxml_integrity/anonymize.py'
  - 'tests/test_anonymize.py'
  - 'evidence/anonymize/**'
---

You are touching the anonymizer. People run it on confidential documents and
then attach the result to a public issue.

- When something cannot be replaced safely, raise `Refused` and write nothing.
  Never guess, and never weaken or remove an existing `Refused` path.
- Every place that can hold a word of the original text is either replaced or
  reported by `leak_scan`. A change that adds a place the anonymizer reads must
  add it to the leak scan in the same change.
- A fix for a leak comes with a test that fails before it: the original word is
  in the output, or the leak scan misses it.
- The anonymized pair must keep every finding of the original pair. Do not
  change what is kept (structure, standard namespaces, field types) without a
  test that shows the findings survive.
- This module has had leak fixes after outside review (0.8.1, 0.8.2). Say in
  your report exactly which inputs you tested and which you did not.
