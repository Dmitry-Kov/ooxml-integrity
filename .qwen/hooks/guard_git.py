#!/usr/bin/env python3
"""PreToolUse hook for Qwen Code: keep an agent off `main` and off the remote.

It reads the hook's JSON from stdin and looks at shell commands only.

  deny  a commit, merge, rebase, cherry-pick or revert while on main or master
  ask   anything that leaves this machine or cannot be undone from it: a push,
        a new tag, `gh` commands that write, a package upload, deleting a
        branch, discarding the working tree, removing tmp/ drafts/ evidence/

"ask" pauses for the person at the terminal, in every approval mode. Where
nobody can answer (headless runs, IDE sessions) Qwen Code treats it as "deny".

This is a guard rail against a mistake, not a sandbox: it reads the command as
text and a determined script can get past it. If it cannot read its input it
exits 0 and the usual approval rules apply.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys

PROTECTED = {"main", "master"}
OPERATORS = {"&&", "||", ";", "|", "&", "(", ")", "|&", ";;"}
ON_BRANCH = {"commit", "merge", "rebase", "cherry-pick", "revert", "am"}
SHELLS = {"bash", "sh", "zsh", "dash", "eval"}
GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
GH_WRITES = {
    "pr": {"create", "merge", "close", "reopen", "edit", "comment", "review", "ready"},
    "issue": {"create", "close", "reopen", "edit", "comment", "delete", "transfer"},
    "release": {"create", "delete", "edit", "upload"},
    "repo": {"edit", "delete", "create", "rename", "archive", "fork", "sync"},
    "workflow": {"run", "enable", "disable"},
    "run": {"rerun", "cancel", "delete"},
    "label": {"create", "edit", "delete"},
    "secret": {"set", "delete"},
    "variable": {"set", "delete"},
}
KEPT_DIRECTORIES = ("tmp", "drafts", "evidence", ".git")


def current_branch(cwd: str) -> str | None:
    try:
        done = subprocess.run(["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
                              capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    name = done.stdout.strip()
    return name if done.returncode == 0 and name else None


def segments(command: str) -> list[list[str]]:
    """The command's simple commands, each as a list of words."""
    lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    out: list[list[str]] = [[]]
    for token in lexer:
        if token in OPERATORS:
            out.append([])
        else:
            out[-1].append(token)
    return [words for words in out if words]


def git_calls(words: list[str]) -> list[list[str]]:
    """Arguments of each `git` invocation among the words, global options removed."""
    calls = []
    for at, word in enumerate(words):
        if word != "git" and not word.endswith("/git"):
            continue
        rest = words[at + 1:]
        while rest and rest[0].startswith("-"):
            rest = rest[2:] if rest[0] in GIT_OPTIONS_WITH_VALUE else rest[1:]
        if rest:
            calls.append(rest)
    return calls


def worse(a: tuple[str, str] | None, b: tuple[str, str] | None) -> tuple[str, str] | None:
    if a is None or b is None:
        return a or b
    return a if a[0] == "deny" or b[0] != "deny" else b


def judge(command: str, branch: str | None, depth: int = 0) -> tuple[str, str] | None:
    """("deny" | "ask", reason) for a shell command, or None to let it through."""
    try:
        parts = segments(command)
    except ValueError:  # quotes the lexer cannot pair, as in some here-documents
        if re.search(r"\b(git\s+(push|commit|tag|merge|rebase)|gh\s+(pr|release|repo|issue)|twine\s+upload)\b",
                     command):
            return "ask", "the command could not be read word by word and names a guarded operation"
        return None

    verdict: tuple[str, str] | None = None
    for words in parts:
        # A script passed to a shell (`bash -c "..."`, `eval "..."`) is one word:
        # read inside it. Other quoted words are data, such as a commit message.
        if depth < 2 and os.path.basename(words[0]) in SHELLS:
            for word in words[1:]:
                if " " in word:
                    verdict = worse(verdict, judge(word, branch, depth + 1))

        for call in git_calls(words):
            sub, args = call[0], call[1:]
            if sub in ("switch", "checkout"):
                names = [a for a in args if not a.startswith("-")]
                if names and "--" not in args:
                    branch = names[0]      # later commands of this line run there
                if sub == "checkout" and ("--" in args or "." in args):
                    verdict = worse(verdict, ("ask", "`git checkout` of paths discards uncommitted changes"))
            elif sub in ON_BRANCH:
                if branch is None:
                    verdict = worse(verdict, ("ask", f"`git {sub}`: the current branch could not be read"))
                elif branch in PROTECTED:
                    verdict = worse(verdict, (
                        "deny", f"`git {sub}` on {branch} is not allowed here. Create a branch first "
                                "(`git switch -c <topic>`); the maintainer merges through a pull request."))
            elif sub == "push":
                verdict = worse(verdict, ("ask", "`git push` publishes commits to the remote"))
            elif sub == "tag":
                listing = not args or any(a in ("-l", "--list", "-n", "--contains", "--points-at", "-v", "--verify")
                                          for a in args)
                if not listing:
                    verdict = worse(verdict, ("ask", "`git tag` creates or deletes a tag; a release tag publishes"))
            elif sub == "branch" and any(a in ("-D", "-d", "--delete", "-M", "-m", "--move") for a in args):
                verdict = worse(verdict, ("ask", "`git branch` would delete or rename a branch"))
            elif sub == "reset" and "--hard" in args:
                verdict = worse(verdict, ("ask", "`git reset --hard` discards uncommitted changes"))
            elif sub == "clean" and any(a.startswith("-") and "f" in a for a in args):
                verdict = worse(verdict, ("ask", "`git clean -f` deletes untracked files, drafts/ and tmp/ among them"))
            elif sub == "restore" and "--staged" not in args:
                verdict = worse(verdict, ("ask", "`git restore` discards uncommitted changes"))
            elif sub == "stash" and args[:1] in (["drop"], ["clear"]):
                verdict = worse(verdict, ("ask", "`git stash drop/clear` deletes saved changes"))
            elif sub == "worktree" and args[:1] == ["remove"]:
                verdict = worse(verdict, ("ask", "`git worktree remove` deletes a working copy"))

        head = os.path.basename(words[0])
        if head == "gh" and len(words) > 2:
            group, action = words[1], words[2]
            if action in GH_WRITES.get(group, ()):
                verdict = worse(verdict, ("ask", f"`gh {group} {action}` changes something on GitHub"))
            elif group == "api" and any(w in ("-X", "--method", "-f", "-F", "--field", "--raw-field", "--input")
                                        for w in words[2:]):
                verdict = worse(verdict, ("ask", "`gh api` with a method or fields writes to GitHub"))
        elif "upload" in words and any(os.path.basename(w) == "twine" for w in words[:words.index("upload")]):
            verdict = worse(verdict, ("ask", "`twine upload` publishes to PyPI; releases go through the Release workflow"))
        elif head == "mcp-publisher" and "publish" in words[1:]:
            verdict = worse(verdict, ("ask", "`mcp-publisher publish` lists a version in the MCP Registry"))
        elif head == "rm":
            for path in (w for w in words[1:] if not w.startswith("-")):
                first = os.path.normpath(path).split(os.sep)[0]
                if first in KEPT_DIRECTORIES and not os.path.isabs(path):
                    verdict = worse(verdict, ("ask", f"`rm` under {first}/, which holds local or historical files"))
    return verdict


def main() -> int:
    try:
        event = json.load(sys.stdin)
        tool_input = event.get("tool_input") or {}
        command = tool_input.get("command")
    except (ValueError, AttributeError):
        return 0
    if not isinstance(command, str) or not command.strip():
        return 0
    cwd = event.get("cwd") or os.environ.get("QWEN_PROJECT_DIR") or os.getcwd()
    directory = tool_input.get("directory") or tool_input.get("dir_path")
    if isinstance(directory, str) and directory:
        cwd = directory if os.path.isabs(directory) else os.path.join(cwd, directory)
    verdict = judge(command, current_branch(cwd))
    if verdict is None:
        return 0
    decision, reason = verdict
    json.dump({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                      "permissionDecision": decision,
                                      "permissionDecisionReason": reason}}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
