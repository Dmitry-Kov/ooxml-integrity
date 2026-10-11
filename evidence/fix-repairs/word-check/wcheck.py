#!/usr/bin/env python3
"""Open one file in Word for Mac, record what happens, close it without saving.

    python3 wcheck.py FILE LABEL [--revisions]

Writes obs/LABEL.json and screenshots in screens/, next to this script; run it
from a working copy of this folder (see README.md).
Prompts: an "unreadable content" prompt is answered No; a following error is
dismissed with OK; Adobe PDFMaker's VBA run-time error 53 (environment) with Return.
--revisions: accept each revision alone, record what is left, undo; then the same
with reject. Nothing is saved.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

H = Path(__file__).resolve().parent
SCREENS, OBS = H / "screens", H / "obs"


def osa(script: str, timeout=60) -> str:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    return (r.stdout.strip() if r.returncode == 0 else "ERR: " + r.stderr.strip())


def windows() -> list[tuple[str, str]]:
    out = osa('''tell application "System Events" to tell process "Microsoft Word"
set r to ""
repeat with w in windows
set r to r & (name of w as text) & "|" & (subrole of w as text) & linefeed
end repeat
return r
end tell''')
    return [tuple(line.split("|", 1)) for line in out.splitlines() if "|" in line]


def dialog_texts() -> list[str]:
    out = osa('''tell application "System Events" to tell process "Microsoft Word"
set d to first window whose subrole is "AXDialog"
set r to ""
repeat with t in (static texts of d)
set r to r & (value of t as text) & " "
end repeat
repeat with b in (buttons of d)
set r to r & "[" & (name of b as text) & "] "
end repeat
return r
end tell''')
    return [out]


def shot_dialog(name: str) -> None:
    geo = osa('''tell application "System Events" to tell process "Microsoft Word"
set d to first window whose subrole is "AXDialog"
set p to position of d
set s to size of d
return (item 1 of p as text) & "," & (item 2 of p as text) & "," & (item 1 of s as text) & "," & (item 2 of s as text)
end tell''')
    subprocess.run(["screencapture", "-x", f"-R{geo}", str(SCREENS / f"{name}.png")])


def click(button: str) -> None:
    osa(f'tell application "System Events" to tell process "Microsoft Word" to click button "{button}" '
        'of (first window whose subrole is "AXDialog")')


def dismiss_vba() -> int:
    n = 0
    while any(w[0] == "Visual Basic for Applications" for w in windows()):
        osa('''tell application "Microsoft Word" to activate
tell application "System Events" to tell process "Microsoft Word"
perform action "AXRaise" of window "Visual Basic for Applications"
key code 36
end tell''')
        n += 1
        time.sleep(1.5)
        if n > 6:
            break
    return n


def docs() -> list[str]:
    out = osa('tell application "Microsoft Word" to get name of documents')
    return [] if out in ("", "missing value") or out.startswith("ERR") else [d.strip() for d in out.split(",")]


def settle(rec: dict, label: str, seconds=25) -> None:
    """Handle prompts until the document is open (or Word gave up)."""
    name = rec["file"]
    deadline = time.time() + seconds
    quiet = 0
    while time.time() < deadline:
        ws = windows()
        if any(s == "AXDialog" for _, s in ws):
            text = dialog_texts()[0]
            k = len(rec["prompts"])
            shot_dialog(f"{label}-prompt{k}")
            if "[No]" in text:
                rec["prompts"].append({"text": text, "choice": "No", "screenshot": f"{label}-prompt{k}.png"})
                click("No")
            elif "[OK]" in text:
                rec["prompts"].append({"text": text, "choice": "OK", "screenshot": f"{label}-prompt{k}.png"})
                click("OK")
            else:
                rec["prompts"].append({"text": text, "choice": "none (unhandled)"})
                return
            time.sleep(2)
            deadline = max(deadline, time.time() + 8)
            continue
        if any(n == "Visual Basic for Applications" for n, _ in ws):
            rec["vba_dismissed"] += dismiss_vba()
            continue
        if name in docs():
            quiet += 1
            if quiet >= 3:
                return
        time.sleep(1)


def read_model() -> dict:
    out = subprocess.run(["osascript", str(H / "wread.applescript")], capture_output=True, text=True,
                         timeout=120).stdout
    comments, revisions = [], []
    for line in out.splitlines():
        f = line.split("\t")
        if f[0] == "COMMENT":
            comments.append({"index": int(f[1]), "author": f[2], "text": f[3], "anchor": f[4]})
        elif f[0] == "REVISION":
            revisions.append({"index": int(f[1]), "type": f[2], "author": f[3], "text": f[4]})
    return {"comments": comments, "revisions": revisions}


def window_shot(label: str) -> str:
    osa('tell application "Microsoft Word" to activate')
    time.sleep(1)
    geo = osa('''tell application "System Events" to tell process "Microsoft Word"
set d to first window whose subrole is "AXStandardWindow"
set p to position of d
set s to size of d
return (item 1 of p as text) & "," & (item 2 of p as text) & "," & (item 1 of s as text) & "," & (item 2 of s as text)
end tell''')
    png = SCREENS / f"{label}.png"
    subprocess.run(["screencapture", "-x", f"-R{geo}", str(png)])
    # the comment margin, full height, at half size, for reading the threads
    subprocess.run(["sips", "-c", "2900", "1000", "--cropOffset", "300", "3760", str(png),
                    "--out", str(SCREENS / f"{label}-margin.png")], capture_output=True)
    subprocess.run(["sips", "-Z", "1450", str(SCREENS / f"{label}-margin.png")], capture_output=True)
    return png.name


def revision_tests() -> list[dict]:
    """Accept, then reject, each revision alone; undo after each."""
    base = read_model()["revisions"]
    sig = lambda r: (r["type"], r["author"], r["text"])
    results = []
    for k in range(1, len(base) + 1):
        for action in ("accept", "reject"):
            res = osa(f'''tell application "Microsoft Word"
set d to active document
{action} (revision {k} of d)
return count of revisions of d
end tell''')
            left = read_model()["revisions"]
            import collections
            gone = [list(k2) for k2 in (collections.Counter(map(sig, base))
                                        - collections.Counter(map(sig, left))).elements()]
            appeared = [list(k2) for k2 in (collections.Counter(map(sig, left))
                                            - collections.Counter(map(sig, base))).elements()]
            osa('tell application "Microsoft Word" to undo active document')
            back = len(read_model()["revisions"])
            results.append({"revision": k, "target": list(sig(base[k - 1])), "action": action,
                            "count_after": res, "removed": gone, "appeared": appeared, "restored_by_undo": back == len(base)})
    return results


def main() -> int:
    path, label = Path(sys.argv[1]).resolve(), sys.argv[2]
    SCREENS.mkdir(exist_ok=True)
    OBS.mkdir(exist_ok=True)
    rec = {"label": label, "file": path.name, "prompts": [], "vba_dismissed": 0,
           "opened_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    subprocess.run(["open", "-a", "Microsoft Word", str(path)])
    time.sleep(4)
    settle(rec, label)
    rec["opened"] = path.name in docs()
    if rec["opened"]:
        rec.update(read_model())
        rec["screenshot"] = window_shot(label)
        if "--revisions" in sys.argv:
            rec["revision_tests"] = revision_tests()
        osa('tell application "Microsoft Word" to close active document saving no')
        time.sleep(2)
        rec["vba_dismissed_on_close"] = dismiss_vba()
        rec["closed"] = path.name not in docs()
    (OBS / f"{label}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in rec.items() if k not in ("revision_tests",)}, ensure_ascii=False)[:1500])
    if "revision_tests" in rec:
        for t in rec["revision_tests"]:
            print("  ", t["action"], t["revision"], t["target"], "-> removed", t["removed"], "appeared", t["appeared"], "undo ok" if t["restored_by_undo"] else "UNDO FAILED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
