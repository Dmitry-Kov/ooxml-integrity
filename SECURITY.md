# Security policy

## Report a vulnerability privately

Use [GitHub private vulnerability reporting](https://github.com/Dmitry-Kov/ooxml-integrity/security/advisories/new)
to contact the repository maintainer, [Dmitrii Kovalev (@Dmitry-Kov)](https://github.com/Dmitry-Kov).
In the repository interface, choose **Security → Advisories → Report a vulnerability**.
This sends a private report to the maintainers. See
[GitHub's reporting instructions](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/report-privately).

Include the checker version or commit, Python/OS and relevant dependency
versions, the command or API call, expected/actual behavior, security impact,
and a minimal reproduction. For resource exhaustion, include input size,
configured archive limits, elapsed time and measured memory if available.
A small synthetic file or generator is preferable to a private document.
Do not put exploitable details, credentials or sensitive documents in a public
issue. If the private form is unavailable, open an
[issue](https://github.com/Dmitry-Kov/ooxml-integrity/issues/new) asking @Dmitry-Kov
to arrange a private channel, with no vulnerability details or attachments.

Review, remediation and disclosure timing are agreed in the private report.
There is no guaranteed response or fix deadline. Ordinary false positives,
missed document defects and installation problems belong in the
[feedback form](https://github.com/Dmitry-Kov/ooxml-integrity/issues/new?template=checker-feedback.yml),
unless they have security impact that needs private handling.

## Maintained versions

Security fixes target the latest published release (currently `0.4.4`).
Older releases do not have a separate maintenance or backport commitment.
Report an issue found on an older version and state whether it also reproduces
on the latest release. An unreleased fix on `main` is not yet in a PyPI package
or necessarily in the browser demo. Check the demo footer and
[release notes](https://github.com/Dmitry-Kov/ooxml-integrity/releases).

## Processing boundaries

The installed checker reads document packages and local fonts. It does not
execute document macros, render documents in Office, or make network/model
calls while checking. It is not a malware scanner or a sandbox, and a passing
integrity result does not establish that a document is safe to open in Office.

OOXML parsing rejects DOCTYPE declarations and disables entity resolution,
DTD loading and parser network access. The bounded ZIP reader checks metadata
before allocation and applies finite [archive budgets](docs/archive-limits.md).
Those byte budgets are not process-memory or CPU ceilings. For untrusted
workloads, use process isolation and external memory/time limits, keep inputs
unchanged during a check, and keep the checker and parsing dependencies updated.

The browser downloads Python, packages and fonts at startup and processes
selected files in its worker. Its input and time limits are described in the
[demo documentation](demo/README.md). Reports, baselines, paths and diagnostic
snippets can reveal document information; review them before sharing or
uploading CI artifacts. Coverage and [known limitations](docs/support-matrix.md)
define what was assessed, rather than a security certification.
