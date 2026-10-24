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

Security fixes target the latest published release (currently `0.8.2`).
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

## Anonymized copies

`ooxml-integrity anonymize` writes copies of a document or pair for sharing a
defect. It replaces the words, people, dates, properties, pictures, embedded
objects, a firm's own schemas (namespaces, prefixes, names, attribute values,
the data binding paths into them and the custom XML markup and smart tags
that name them in the document), and the other places listed in
[what is replaced](docs/anonymize.md#what-is-replaced); what it cannot replace
safely it [refuses](docs/anonymize.md#what-is-refused). It does not
make a document anonymous in every sense: the shape of the text (word lengths,
capitals and digits, which words repeat), the package structure and the items
under [what is kept](docs/anonymize.md#what-is-kept) remain, and a reader who
knows the original can recognise it from its shape. The leak scan looks for
words of the original text; it cannot judge what the shape reveals. Open the
copies before sharing them.

A word, name or value of the original that survives in a copy is a security
defect of the anonymizer. Report it privately, as above, with a synthetic
document that shows it, never with the confidential original.

### Copies made by 0.5.0 to 0.8.1

Those versions kept the names that custom XML markup and smart tags give of
a firm's schema in the document itself, and settings that go with them; in a
part that is not well-formed XML, also hyperlink addresses and other values
a well-formed part loses. The leak scan looked there for two consecutive
words of the text at most, so the report said nothing was left:

- **Custom XML markup** (`<w:customXml w:uri="https://firm.example/..."
  w:element="ClientName">`, around runs, paragraphs, table rows or cells):
  the element name (`w:element`), and in its properties (`w:customXmlPr`)
  the names of its attributes (`<w:attr w:name="...">`) and its placeholder
  text (`<w:placeholder w:val="...">`). The namespace URI (since 0.5.2) and
  the attribute values were replaced. An element without `w:uri` kept its
  name too.
- **Smart tags in a firm's namespace** (`w:smartTag`, such as a document
  management system's): the element and attribute names, as above.
- **The settings part** (`word/settings.xml`): each smart tag type's name and
  recognizer address (`<w:smartTagType w:name="..." w:url="...">`), and its
  namespace when no smart tag in the package used it; the schema library's
  schema and manifest locations (`sl:schemaLocation`, `sl:manifestLocation`,
  often file paths with a user or server name), and its namespace when
  nothing else in the package named it; the identifier of the transform the
  document is saved through (`<w:saveThroughXslt w:solutionID="...">`).
- In a part that is not well-formed XML (listed as "read as raw text"), the
  same names and text, and the namespace URI of custom XML markup and smart
  tags when no well-formed part declared that namespace. Such a part also
  kept these values, which a well-formed part loses: hyperlink addresses on
  VML shapes (`<v:shape href="..." o:href="...">`), external relationship
  targets (`TargetMode="External"`, in a relationships part that is not
  well-formed), shape names that VML repeats as ids (`<v:shape id="...">`)
  and the references to them, numbering formats (`w:lvlText`), custom style
  ids and names and their uses (`w:pStyle`, `w:basedOn`, ...), the names of
  form fields, building blocks and mail merge fields (`<w:name w:val="...">`),
  data binding paths (`w:dataBinding`), and the attached schema and the
  schema library's namespace and locations when no well-formed part named
  that namespace.

Office's own smart tags keep their names on purpose (`City`, `PersonName` in
`urn:schemas-microsoft-com:office:smarttags`, `GivenName` in
`urn:schemas:contacts`, a namespace copies made by 0.5.2 to 0.8.1 replaced):
they say what kind of word was tagged.

Before sharing a copy made by one of those versions, make it again with
0.8.2 or later. If that is not possible, open `word/settings.xml` and the
parts with text (`word/document.xml`, headers, footers, notes, comments) and
check every `w:customXml` and `w:smartTag` element (its `w:element` and the
`w:attr` names and `w:placeholder` text that follow it), every
`w:smartTagType`, `sl:schema` and `w:saveThroughXslt`, for example
`unzip -p copy.docx word/document.xml | grep -oE '<w:(customXml|smartTag|attr|placeholder) [^>]*>' | sort -u`.
Also open every part the report listed as read as raw text and check the
values above in it, for example, when that part is the document,
`unzip -p copy.docx word/document.xml | grep -oE '(href|Target|ShapeID|xpath)="[^"]*"|<(v:shape|w:lvlText|w:name|w:style|w:pStyle|sl:schema|w:attachedSchema) [^>]*>' | sort -u`.

### Copies made by 0.5.0 to 0.8.0

An external review of 0.8.0 found three places where those versions kept
values of the original. The leak scan reported none of them (it looked there
for two consecutive words of the text at most), so the report said nothing
was left:

- **Attributes in a firm's own namespace.** An attribute in a namespace that
  is neither the format's nor Office's (`<w:p a:client="..."
  xmlns:a="https://firm.example/...">`) had its namespace and name replaced
  since 0.5.2, never its value.
- **Data binding paths.** A content control bound to custom XML data
  (`w:dataBinding`) kept the string literals of its path, such as `Acme` in
  `[@name='Acme']`. Those copies' bindings also select nothing, because the
  data the literal names was replaced.
- **Namespace prefixes.** A prefix bound to a firm's namespace kept its name,
  as in `<Acme:Contract xmlns:Acme="...">`.

A fourth place was kept then and still is: a part that is not well-formed XML
(the report lists it as "read as raw text") keeps its markup, and with it the
attribute values the rules do not name. The leak scan of those versions read
such an attribute's name instead of its value, so it did not report them; it
reads the values now.

Copies made by 0.5.0 and 0.5.1 also kept the namespace URIs and the element
and attribute names of a firm's schemas (fixed in 0.5.2).

Before sharing a copy made by one of those versions, make it again with
0.8.2 or later, which replaces the first three and the places in the section
above, and reports the fourth. If that is not possible, open the copy's XML
parts
(`word/document.xml`, headers, footers, notes, comments, `customXml/item*.xml`)
and check three things: the value of every attribute whose prefix is bound to
a namespace outside `schemas.openxmlformats.org`, `schemas.microsoft.com` and
the other standard ones; every quoted string in a `w:xpath`; and every
`xmlns:` prefix bound to such a namespace. Also open every part the report
listed as read as raw text. Searching all parts for the names that matter
finds all of these, for example `unzip -p copy.docx | grep -c -i "acme"`.

The same versions also wrote over an input whose path, or a link to it, was
one of the output names (`document.docx`, `source.docx`, `edited.docx` in the
output directory): always from Python, and from the command line with
`--force`. That loses the original rather than exposing it; such a run then
checked the copy against itself, so its "findings reproduced" said nothing.
An output that is, or links to, an input is now refused before anything is
written.
