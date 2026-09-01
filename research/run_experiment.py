#!/usr/bin/env python3
"""
Run: each mutator -> inspector -> "did it survive LibreOffice" check.
Plus an accumulation scenario: 20 edit cycles, as in DELEGATE-52.
"""
import os, sys, shutil, subprocess, json, zipfile
from collections import Counter
from ooxml_integrity import check as inspect, summarize, ERROR, WARN
from mutate import MUTATORS, m_pythondocx_settext, m_llm_copy_clause, m_llm_raw_xml_value

BASE = os.environ.get('DI_BASE', '../corpus/base.docx')
OUT = os.environ.get('DI_OUT', 'out')


def lo_converts(path):
    """LibreOffice as a proxy: does the file convert at all."""
    d = '/tmp/loconv'
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)
    r = subprocess.run(['soffice', '--headless', '--convert-to', 'pdf', '--outdir', d, path],
                       capture_output=True, timeout=180)
    pdf = os.path.join(d, os.path.basename(path).replace('.docx', '.pdf'))
    return os.path.exists(pdf) and os.path.getsize(pdf) > 1000


def features(path):
    """Counts how many meaningful constructs survived the edit."""
    W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    from lxml import etree
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            doc = etree.fromstring(z.read('word/document.xml'))
    except Exception:
        return None
    cnt = lambda t: len(list(doc.iter(W + t)))
    return {
        'runs':        cnt('r'),
        'styles_ref':  cnt('pStyle') + cnt('rStyle') + cnt('tblStyle'),
        'numbering':   cnt('numPr'),
        'footnote_rf': cnt('footnoteReference'),
        'comment_rf':  cnt('commentReference'),
        'tracked':     cnt('ins') + cnt('del'),
        'sdt':         cnt('sdt'),
        'tables':      cnt('tbl'),
        'images':      cnt('drawing'),
        'hyperlinks':  cnt('hyperlink'),
        'parts':       len(names),
    }


def pct(now, base):
    if base == 0:
        return '—'
    return f'{round(100 * now / base)}%'


def main():
    os.makedirs(OUT, exist_ok=True)
    base_f = features(BASE)
    base_s = summarize(inspect(BASE))
    print(f'BASELINE  errors={base_s["error"]} warnings={base_s["warn"]}  |  '
          f'parts={base_f["parts"]} runs={base_f["runs"]}\n')

    rows = []
    for key, desc, fn in MUTATORS:
        dst = f'{OUT}/{key}.docx'
        try:
            fn(BASE, dst)
        except Exception as e:
            rows.append((key, desc, 'CRASH', str(e)[:60], None, None))
            continue
        fs = inspect(dst)
        s = summarize(fs)
        feat = features(dst)
        conv = lo_converts(dst)
        rows.append((key, desc, s, fs, feat, conv))

    print('=' * 108)
    print(f'{"mutator":<17}{"inspector":<16}{"LO":<5}{"styles":<8}{"numb":<8}{"fnotes":<8}'
          f'{"comments":<9}{"revs":<8}{"sdt":<7}{"img":<6}')
    print('-' * 108)
    for key, desc, s, fs, feat, conv in rows:
        if s == 'CRASH':
            print(f'{key:<17}{"mutator crashed":<16}')
            continue
        insp = f'E{s["error"]} W{s["warn"]}'
        lo = 'ok' if conv else 'FAIL'
        print(f'{key:<17}{insp:<16}{lo:<5}'
              f'{pct(feat["styles_ref"], base_f["styles_ref"]):<8}'
              f'{pct(feat["numbering"], base_f["numbering"]):<8}'
              f'{pct(feat["footnote_rf"], base_f["footnote_rf"]):<8}'
              f'{pct(feat["comment_rf"], base_f["comment_rf"]):<9}'
              f'{pct(feat["tracked"], base_f["tracked"]):<8}'
              f'{pct(feat["sdt"], base_f["sdt"]):<7}'
              f'{pct(feat["images"], base_f["images"]):<6}')
    print('=' * 108)

    print('\nDEFECTS FOUND, BY MUTATOR\n')
    for key, desc, s, fs, feat, conv in rows:
        if s == 'CRASH':
            continue
        real = [f for f in fs if f.severity in (ERROR, WARN)]
        print(f'--- {key}  ({desc})')
        if not real:
            print('    no structural defects found')
        seen = set()
        for f in real:
            if f.code in seen:
                continue
            seen.add(f.code)
            n = sum(1 for g in real if g.code == f.code)
            mult = f' x{n}' if n > 1 else ''
            print(f'    [{f.severity.value.upper():5}] {f.code}{mult}  {f.msg}')
        print()

    # ---- accumulation: 20 cycles ----
    print('=' * 108)
    print('ACCUMULATION: 20 edit cycles, as in DELEGATE-52\n')
    cur = f'{OUT}/cycle_00.docx'
    shutil.copy(BASE, cur)
    cycle_ops = [m_pythondocx_settext, m_llm_raw_xml_value, m_llm_copy_clause]
    print(f'{"cycle":<7}{"errors":<9}{"warns":<8}{"runs":<8}{"styles":<8}{"fnotes":<9}'
          f'{"comments":<10}{"revs":<9}{"LO":<6}')
    print('-' * 70)
    for i in range(1, 21):
        nxt = f'{OUT}/cycle_{i:02d}.docx'
        op = cycle_ops[(i - 1) % len(cycle_ops)]
        try:
            op(cur, nxt)
        except Exception as e:
            print(f'{i:<7}mutator crashed: {str(e)[:50]}')
            break
        fs = inspect(nxt)
        s = summarize(fs)
        feat = features(nxt)
        if feat is None:
            print(f'{i:<7}file no longer readable')
            break
        if i in (1, 2, 3, 4, 6, 8, 10, 14, 20):
            conv = 'ok' if lo_converts(nxt) else 'FAIL'
            print(f'{i:<7}{s["error"]:<9}{s["warn"]:<8}'
                  f'{pct(feat["runs"], base_f["runs"]):<8}'
                  f'{pct(feat["styles_ref"], base_f["styles_ref"]):<8}'
                  f'{pct(feat["footnote_rf"], base_f["footnote_rf"]):<9}'
                  f'{pct(feat["comment_rf"], base_f["comment_rf"]):<10}'
                  f'{pct(feat["tracked"], base_f["tracked"]):<9}{conv:<6}')
        cur = nxt


if __name__ == '__main__':
    main()
