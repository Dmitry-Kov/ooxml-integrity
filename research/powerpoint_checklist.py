#!/usr/bin/env python3
"""Print the per-shape predictions to check against a real renderer.

Pair this with `outline_deck.py`. The outlined copy makes overflow visible; this
prints what the checker predicts for every shape, so the comparison is a list of
yes/no questions rather than an impression.

The predictions are computed, never typed. Two fixture labels in this corpus were
already wrong on the first pass because I had guessed them, so the checklist
derives everything from the same code path the tool uses.

    python powerpoint_checklist.py > ../POWERPOINT_CHECK.md
    python powerpoint_checklist.py --ru > ../POWERPOINT_CHECK.ru.md

`--ru` only translates the prose; every number comes from the same call.
"""
from __future__ import annotations

import argparse
import os
import sys

from ooxml_integrity import check_pptx
from ooxml_integrity.fonts import measurement_available, resolve_face
from ooxml_integrity.pptx_layout import layout_shape, read_deck

DECK = os.environ.get("DI_PPTX", "../corpus/deck.pptx")

#: Shapes whose rendering is legitimately renderer-dependent, so a disagreement
#: proves nothing about the measurement. Named here, before the comparison, so
#: none of them can be excused after the fact.
EXCLUDED = {
    "AUTOFIT_shrink_text": (
        "normAutofit with no stored fontScale - PowerPoint recomputes the "
        "shrink on open, so what it draws is its own decision, not the file's",
        "normAutofit без записанного fontScale - PowerPoint пересчитывает "
        "сжатие при открытии, так что рисует он своё решение, а не файла",
    ),
    "AUTOFIT_grow_shape": (
        "spAutoFit - PowerPoint grows the box to the text, so the stored box "
        "height is not what gets drawn",
        "spAutoFit - PowerPoint растит блок под текст, так что записанная "
        "высота блока это не то, что рисуется",
    ),
    "FIT_unknown_font": (
        "declares a face nobody has; PowerPoint substitutes its own choice, "
        "and the checker already says the number is a guess",
        "объявляет шрифт, которого ни у кого нет; PowerPoint подставит свой, "
        "а чекер и так говорит, что число это догадка",
    ),
}

EN = {
    "title": "Checking the reference deck against a real renderer",
    "deck": "Deck",
    "measured": "Measured with",
    "calibri": "Calibri resolved to",
    "intro": (
        "Open `corpus/deck_outlined.pptx`. Every text box has a thin magenta "
        "outline. For each shape below the only question is whether the text "
        "stays inside that outline."),
    "warn": (
        "**Do not click into a text box, and close without saving.** Clicking "
        "into a shape with shrink-to-fit makes PowerPoint recompute and store a "
        "new font scale, which edits the fixture."),
    "slide": "Slide",
    "head": "| shape | text | box W×H (pt) | text needs (pt) | prediction |",
    "excluded": "**excluded**",
    "right": "text should cross the **right** edge (needs {w:.0f}pt of width)",
    "bottom": ("text should cross the **bottom** edge ({r:.0%} of the box, "
               "{n})"),
    "inside": "text should stay **inside** ({r:.0%} of the box, {n})",
    "line_1": "{n} line",
    "line_few": "{n} lines",
    "line_n": "{n} lines",
    "unmeasured": "not measured",
    "close_h": "Where a disagreement is most likely",
    "close_p": (
        "These shapes have a line filling more than 95% of the usable width. "
        "One wrap decision either way changes the line count, and that is the "
        "first place a real renderer should differ from this model - kerning "
        "and hinting are enough to move it."),
    "close_row": "- `{name}` - widest line fills {fill:.1%} of the box, {n}",
    "close_none": "- none",
    "mean_h": "What each outcome would mean",
    "mean": (
        "- A shape predicted **inside** whose text crosses the line -> the "
        "model under-reports, and the tool would miss a real defect.\n"
        "- A shape predicted to **cross** whose text stays inside -> the model "
        "over-reports, which produces false positives in someone's CI.\n"
        "- Agreement on all of them -> the 1.2 line-spacing constant and the "
        "inset arithmetic hold against the renderer the documents are made "
        "for, which is the one claim the README cannot currently make."),
}

RU = {
    "title": "Проверка эталонной деки против настоящего рендерера",
    "deck": "Дека",
    "measured": "Измерено шрифтом",
    "calibri": "Calibri разрешился в",
    "intro": (
        "Открой `corpus/deck_outlined.pptx`. У каждого текстового блока тонкий "
        "магентовый контур. По каждому шейпу ниже вопрос один: текст остаётся "
        "внутри контура или выходит за него."),
    "warn": (
        "**Не щёлкай внутрь текстовых блоков и закрой без сохранения.** Если "
        "войти курсором в шейп со shrink-to-fit, PowerPoint пересчитает "
        "масштаб шрифта и запишет его в файл - то есть отредактирует фикстуру."),
    "slide": "Слайд",
    "head": "| шейп | текст | блок Ш×В (pt) | тексту нужно (pt) | предсказание |",
    "excluded": "**исключён**",
    "right": "текст должен выйти за **правый** край (нужно {w:.0f}pt ширины)",
    "bottom": ("текст должен выйти за **нижний** край ({r:.0%} от блока, "
               "{n})"),
    "inside": "текст должен остаться **внутри** ({r:.0%} от блока, {n})",
    "line_1": "{n} строка",
    "line_few": "{n} строки",
    "line_n": "{n} строк",
    "unmeasured": "не измерено",
    "close_h": "Где расхождение наиболее вероятно",
    "close_p": (
        "У этих шейпов строка заполняет больше 95% полезной ширины. Одно "
        "решение о переносе в любую сторону меняет число строк - и это первое "
        "место, где настоящий рендерер должен разойтись с моделью: кернинга и "
        "хинтинга достаточно, чтобы сдвинуть перенос."),
    "close_row": "- `{name}` - широчайшая строка занимает {fill:.1%} блока, {n}",
    "close_none": "- нет таких",
    "mean_h": "Что означает каждый исход",
    "mean": (
        "- Шейп с предсказанием **внутри**, чей текст вышел за контур -> "
        "модель недооценивает, и инструмент пропустил бы настоящий дефект.\n"
        "- Шейп с предсказанием **выйдет**, чей текст остался внутри -> модель "
        "переоценивает, а это ложные срабатывания в чьём-то CI.\n"
        "- Согласие по всем -> константа межстрочного 1.2 и арифметика "
        "отступов держатся против того рендерера, для которого документы и "
        "делаются. Именно этого утверждения в README сейчас нет."),
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ru", action="store_true",
                    help="print the prose in Russian; numbers are identical")
    ap.add_argument("deck", nargs="?", default=DECK)
    args = ap.parse_args(argv)
    t = RU if args.ru else EN
    ru = args.ru

    def lines(n: int) -> str:
        """One / few / many, because Russian needs three forms and 3 строк is wrong."""
        if not ru:
            return t["line_1" if n == 1 else "line_n"].format(n=n)
        if n % 10 == 1 and n % 100 != 11:
            key = "line_1"
        elif n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
            key = "line_few"
        else:
            key = "line_n"
        return t[key].format(n=n)

    _, detail = measurement_available()
    deck = read_deck(args.deck)
    calibri = resolve_face("Calibri")

    print(f"# {t['title']}\n")
    print(f"{t['deck']}: `{args.deck}`  ")
    # the tool's own phrasing reads oddly after a Russian label
    print(f"{t['measured']}: "
          f"{detail.replace('measuring with ', '') if ru else detail}  ")
    print(f"{t['calibri']} **{calibri.family}** (`{calibri.match}`)\n")
    print(t["intro"] + "\n")
    print(t["warn"] + "\n")

    slides: dict[int, list] = {}
    for s in deck.shapes:
        slides.setdefault(s.slide, []).append(s)

    close_calls = []
    for slide in sorted(slides):
        print(f"\n## {t['slide']} {slide}\n")
        print(t["head"])
        print("|---|---|---|---|---|")
        for s in sorted(slides[slide], key=lambda x: (x.top, x.left)):
            text = " ".join(p.text for p in s.paragraphs).strip()
            snippet = (text[:34] + "…") if len(text) > 35 else text
            snippet = snippet.replace("|", "\\|") or "—"
            r = layout_shape(s)
            if r is None or not r.measured:
                print(f"| `{s.name}` | {snippet} | — | {t['unmeasured']} | — |")
                continue

            if s.name in EXCLUDED:
                why = EXCLUDED[s.name][1 if ru else 0]
                pred = f"{t['excluded']} — {why}"
            elif not s.wrap and r.widest_line_pt > r.box_width_pt:
                pred = t["right"].format(w=r.widest_line_pt)
            elif r.vertical_overflow_ratio > 1.0:
                pred = t["bottom"].format(r=r.vertical_overflow_ratio,
                                          n=lines(r.lines))
            else:
                pred = t["inside"].format(r=r.vertical_overflow_ratio,
                                          n=lines(r.lines))
            print(f"| `{s.name}` | {snippet} | "
                  f"{r.box_width_pt:.0f} × {r.box_height_pt:.0f} | "
                  f"{r.text_height_pt:.0f} | {pred} |")

            if s.name in EXCLUDED:
                continue
            fill = r.widest_line_pt / r.box_width_pt if r.box_width_pt else 0
            # Near the edge, not past it by miles: a line at 99% of the width is
            # one wrap decision from a different line count, while one at 166%
            # (wrap is off) is not in doubt at all.
            if 0.95 < fill < 1.10:
                close_calls.append((s.name, fill, r.lines))

    print(f"\n## {t['close_h']}\n")
    print(t["close_p"] + "\n")
    for name, fill, n in sorted(close_calls, key=lambda x: -x[1]):
        print(t["close_row"].format(name=name, fill=fill, n=lines(n)))
    if not close_calls:
        print(t["close_none"])

    print(f"\n## {t['mean_h']}\n")
    print(t["mean"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
