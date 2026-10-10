# Checking from an agent: `ooxml-integrity mcp`

An agent that edits a `.docx` or `.pptx` can check its own output before it
returns the file. `ooxml-integrity mcp` is a
[Model Context Protocol](https://modelcontextprotocol.io/) server with two
tools, `check` and `compare`, which run the same checks as the
[CLI](../README.md#two-questions). The server runs on your machine as a
subprocess of the agent's client. It talks over stdin and stdout, opens no
socket and reads only the files a call names. It adds no dependency.

The server is new. Until [compatibility and upgrades](compatibility.md) lists
it among the machine-readable contracts, its tool names and result shape may
change between releases; the JSON report inside a result is the CLI's and
keeps its own contract.

```bash
pip install ooxml-integrity
```

You do not start the server yourself; the client starts it with
`ooxml-integrity mcp`. If the console script is not on `PATH`, give the
client `python -m ooxml_integrity mcp` instead, with the interpreter that has
the package installed.

## Client configuration

### Claude Code

```bash
claude mcp add ooxml-integrity -- ooxml-integrity mcp
```

Options such as `--scope project` or `-e KEY=value` go after the server name:
`-e` takes several values, so a name after it is read as another variable.
With `--scope project` the entry goes into `.mcp.json` at the project root,
which can be committed:

```json
{
  "mcpServers": {
    "ooxml-integrity": {
      "command": "ooxml-integrity",
      "args": ["mcp"]
    }
  }
}
```

Claude Code asks for approval before it starts a server from a project's
`.mcp.json`.

### Codex

```bash
codex mcp add ooxml-integrity -- ooxml-integrity mcp
```

This writes the following to `~/.codex/config.toml`, which can also be edited
directly:

```toml
[mcp_servers.ooxml-integrity]
command = "ooxml-integrity"
args = ["mcp"]
```

### OpenCode

In `opencode.json` at the project root, or in the global OpenCode config:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "ooxml-integrity": {
      "type": "local",
      "command": ["ooxml-integrity", "mcp"],
      "enabled": true
    }
  }
}
```

### Server options

Server options go after `mcp` in the client's arguments, for example
`["mcp", "--fail-on", "warn"]`:

| option | effect |
|---|---|
| `--config PATH` | use this config file |
| `--no-config` | ignore any config file |
| `--fail-on SEVERITY` | `error` (default), `warn` or `info`; overrides the config's `fail-on` |

Without `--config` the server looks for a config the way `check` does,
upwards from its working directory: `.ooxml-integrity.toml`, or a
`[tool.ooxml-integrity]` table in `pyproject.toml`.

The server reads the config once, when it starts. The client starts it before
the agent edits anything, so a config the agent writes or edits later, an
`[[ignore]]` entry for instance, is not applied: the verdict says
`config changed since the server started` and the run uses the copy read at
start. Restart the server to apply a change you made. A call cannot change
the config either: the agent can declare a change it was asked to make (see
[expectations](#changes-the-edit-was-asked-to-make)), but it cannot turn a
rule off or lower the threshold.

The config in the repository is still the agent's to edit before a server
starts, for example in a later session. For a check the agent cannot
influence, give the server a config outside the repository it edits with
`--config`, or none with `--no-config`. Whatever config is used, the verdict
names every finding it suppressed and the file that suppressed it.

## Tools

| tool | arguments | same as |
|---|---|---|
| `check` | `path` | `ooxml-integrity check PATH --json --coverage` |
| `compare` | `source`, `edited`, optional `expect` | `ooxml-integrity check EDITED --against SOURCE --json --coverage` |

`check` inspects one file on its own. Without the original it cannot see
what an edit removed, such as a deleted comment or an accepted revision, so an
agent with the original should call `compare`. For a `.pptx`, `compare` runs
the layout checks and reports the comparison as not performed (`FID000`), as
the CLI does.

### Paths

A path is absolute, or relative to the server's working directory, which the
client chooses; absolute paths avoid the question. `~` is expanded. The path
must name a regular file. A URL (`https://...`, `file:...`, any `scheme:`) or
a network path (`//host/share/...`, `\\host\share\...`) is rejected without
any attempt to read it, and so is a directory or a missing file. The server
never downloads, writes or deletes anything. A path is not confined to the
project: like the agent's own file tools, the server can read any file the
user who runs it can read.

## Results

The text content has two parts: a one-line verdict, then the JSON report that
`--json --coverage` prints. Clients that negotiate protocol version
2025-06-18 or later also get `structuredContent`:

```json
{
  "verdict": "runs/t4_fast_fee/agreement.docx: 2 error(s), ...",
  "exit_code": 1,
  "report": {"version": "...", "fail_on": "error", "files": [...]}
}
```

`exit_code` is what `ooxml-integrity check` would exit with: `1` when a
finding is at or above `fail-on`, otherwise `0`. Findings are not tool errors:
the result has `isError: false` whatever the document contains. `isError:
true` means the call could not run, such as a URL, a missing file, an invalid
expectation or an unreadable config, and its text says why.

The verdict starts with the CLI's summary line and says what it means:

```
runs/t4_fast_fee/agreement.docx: 2 error(s), 0 warning(s), 1 info - fails at fail-on error: CMT005, FID001; not fully checked: 2 unsupported (see coverage)
runs/t2_pres/agreement.docx: 0 error(s), 0 warning(s), 4 info - nothing at or above fail-on error; below it: FID002 (2), FID012 (2); not fully checked: 1 skipped, 2 unsupported (see coverage)
corpus/base.docx: 0 error(s), 0 warning(s), 0 info - no findings in checked surfaces; not fully checked: 6 skipped, 2 unsupported (see coverage)
plain.docx: 0 error(s), 0 warning(s), 0 info - clean
```

It says `clean` only when there are no findings and
[coverage](coverage.md) has no `estimated`, `skipped` or `unsupported`
item, the same rule `check --coverage` follows. Otherwise a file with no
findings has `no findings in checked surfaces`. The `not fully checked` counts
show what the report's `coverage` block explains item by item. A `.docx`
checked without its original always has the six `docx.fidelity.*` items
skipped, so `check` alone does not call it clean. The verdict also names the
findings accepted as expected and the findings the config suppressed, with
the config file (`1 finding(s) suppressed by config .ooxml-integrity.toml:
CMT005`), and says when the config on disk changed after the server started.

## Changes the edit was asked to make

Some requested edits remove what `compare` protects: accepting a tracked
insertion lowers the revision count (`FID001`), and rewriting a header
untracked changes that story (`FID007`). The agent declares such a change in
`expect`, in the format of an `[[expect]]` entry in the
[configuration](configuration.md#changes-the-edit-was-asked-to-make), without
`path`, because the expectation applies to the edited file of the call:

```json
{
  "source": "/work/contract.docx",
  "edited": "/work/contract-accepted.docx",
  "expect": [
    {
      "code": "FID001",
      "reason": "the user asked to accept Counsel's pending insertion",
      "match": {"tag": "ins", "before": 2, "after": 1}
    }
  ]
}
```

`code` and `reason` are required; `match` holds single values; `required:
false` allows a finding without requiring it. A matching finding moves to the
report's `expected` list with its reason. An expectation that matches nothing
is an `EXP001` error, because the requested change did not happen, or not the
way it was declared. Expectations in the config file apply as well.

## Protocol

MCP over stdio: JSON-RPC 2.0, one message per line, UTF-8. The server
implements `initialize`, `ping`, `tools/list` and `tools/call`, and ignores
notifications. It offers protocol versions 2025-11-25, 2025-06-18, 2025-03-26
and 2024-11-05. A client that asks for another version is offered 2025-11-25,
and decides whether to continue, as the specification describes. JSON-RPC
batches are not accepted. Anything a check prints goes to stderr, which
clients keep as the server's log, so stdout carries only protocol messages.

```
-> {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"example","version":"1"}}}
<- {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-06-18","capabilities":{"tools":{"listChanged":false}},"serverInfo":{"name":"ooxml-integrity","version":"..."},"instructions":"..."}}
-> {"jsonrpc":"2.0","method":"notifications/initialized"}
-> {"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"check","arguments":{"path":"https://example.com/a.docx"}}}
<- {"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"path: 'https://example.com/a.docx' is a URL; only files on this machine are read, nothing is downloaded"}],"isError":true}}
```

The server does not use the official `mcp` package. The whole server, tool
descriptions included, is about 400 lines of the package's own code. `mcp`
2.3.0 requires Python 3.10, while the checker supports 3.9, and installs 27
other distributions, among them an HTTP server stack and cryptography, for a
server that opens no socket.
