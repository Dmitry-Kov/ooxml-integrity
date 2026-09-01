#!/usr/bin/env python3
"""Put several renderers' measurements side by side.

Each input is a `--json` file written by calibrate_pptx.py, so every column was
produced by the same measurement code and the same model - a difference between
columns is a difference between renderers, not between harnesses.

    python compare_renderers.py a.json b.json c.json

What the report is for. A single renderer agreeing with the model shows the
model is sane for that renderer. Several renderers *disagreeing with each other*
shows something else, and something more useful: that the shape sits at a margin
where no measurement can be authoritative, which is exactly what a borderline
band is supposed to cover. Those rows are called out separately rather than
averaged away.
"""
from __future__ import annotations

import argparse
import json
import sys


def load(paths: list[str]) -> list[dict]:
    out = []
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
        if "shapes" not in d:
            print(f"compare_renderers: {p} is not a calibrate_pptx --json file",
                  file=sys.stderr)
            raise SystemExit(2)
        out.append(d)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("json", nargs="+", help="files written by calibrate_pptx --json")
    ap.add_argument("--markdown", action="store_true",
                    help="emit a markdown table instead of a fixed-width one")
    args = ap.parse_args(argv)

    runs = load(args.json)
    labels = [r["renderer"] for r in runs]
    short = [l.split(" (")[0] for l in labels]

    # Shape order comes from the first run; every run measured the same deck.
    order = [s["shape"] for s in runs[0]["shapes"]]
    by_run = [{s["shape"]: s for s in r["shapes"]} for r in runs]

    missing = [name for name in order if any(name not in b for b in by_run)]
    if missing:
        print(f"compare_renderers: {missing[0]!r} is not in every file; the "
              f"runs are of different decks", file=sys.stderr)
        return 2

    agree_all: list[str] = []
    split: list[tuple[str, int, list[int]]] = []

    if args.markdown:
        print("| shape | model | " + " | ".join(short) + " |")
        print("|---|---|" + "---|" * len(short))
    else:
        w = max(len(n) for n in order) + 2
        print(f'{"shape":{w}}{"model":7}' + "".join(f"{s[:16]:18}" for s in short))
        print("-" * (w + 7 + 18 * len(short)))

    for name in order:
        pred = by_run[0][name]["lines_predicted"]
        got = [b[name]["lines_rendered"] for b in by_run]
        cells = [f"{g}" + ("" if g == pred else "  <-") for g in got]
        if args.markdown:
            print(f"| `{name}` | {pred} | "
                  + " | ".join(("**" + c.replace("  <-", "**") if "<-" in c
                                else c) for c in cells) + " |")
        else:
            print(f'{name:{w}}{pred:<7}' + "".join(f"{c:18}" for c in cells))
        if all(g == pred for g in got):
            agree_all.append(name)
        if len(set(got)) > 1:
            split.append((name, pred, got))

    print()
    print(f"shapes                     {len(order)}")
    print(f"all renderers match model  {len(agree_all)}")
    for run, label in zip(runs, labels):
        lc = run["line_count"]
        pitch = run.get("pitch_delta_median")
        worst = run.get("pitch_delta_worst")
        extra = ""
        if pitch is not None:
            extra = (f"   pitch median {pitch * 100:.3f}%  "
                     f"worst {worst * 100:.3f}%")
        print(f"  {label[:52]:54}{lc['exact']}/{lc['total']} exact{extra}")

    if split:
        print("\nrenderers that disagree with each other:")
        for name, pred, got in split:
            pairs = ", ".join(f"{s}={g}" for s, g in zip(short, got))
            print(f"  {name}  model={pred}  {pairs}")
        print("\nA shape here cannot be settled by measuring harder: two real\n"
              "engines lay the same string out differently. This is what the\n"
              "borderline band in pptx_checks.BORDERLINE is for, and the band's\n"
              "justification is now three engines rather than one.")
    else:
        print("\nno shape divides the renderers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
