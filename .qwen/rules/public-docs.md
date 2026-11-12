---
description: Public documents carry only sourced numbers and working examples
paths:
  - 'README.md'
  - 'CHANGELOG.md'
  - 'docs/**'
  - 'demo/**'
  - 'server.json'
---

You are touching text that users and other projects read.

- A number needs a source: a file under `evidence/` or a command you ran now.
  Name the scope with it (which documents, which versions). Do not round up,
  and do not turn "attempts on two documents" into a general rate.
- An example must work as written. Action examples and install lines name the
  published tag, not `main` and not a version that is not on PyPI yet.
- `README.md` must keep the line `<!-- mcp-name: io.github.Dmitry-Kov/ooxml-integrity -->`;
  the MCP Registry refuses the package without it.
- The README is also the PyPI page. Keep the first screen short; long tables
  belong in `docs/rules.md`, `docs/upstream.md` and `docs/research.md`.
- When you move or rename a section, search the repository for links to its
  anchor and update them.
- The status of an upstream issue or pull request is checked on GitHub on the
  day you write it, with `gh`, and written with that date when it can change.
- Files under `docs/releases/` describe a published version. Do not edit the
  notes of a release that is already out, except to fix a broken link.
- Plain wording. No claims the evidence does not make: the project is
  research-alpha, and accuracy on customer documents has not been measured.
