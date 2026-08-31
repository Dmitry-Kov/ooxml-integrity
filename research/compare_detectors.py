#!/usr/bin/env python3
"""
The headline table: what each verification approach actually catches.

  1. well-formed XML   - what any parser does
  2. schema validation - what Office-o-tron, OfficeCLI validate and friends do
  3. rendering         - what Anthropic's official pptx/docx skill does
                         (LibreOffice -> PDF -> image -> "look at it with fresh eyes")
  4. structural inspector + fidelity check against the source (this prototype)
"""
import os, shutil, subprocess, zipfile
from lxml import etree
from docx_integrity import check as inspect, ERROR, WARN
from docx_integrity import compare
from mutate import MUTATORS

BASE = os.environ.get('DI_BASE', '../corpus/base.docx')
OUT = os.environ.get('DI_OUT', 'out')


def wellformed(path):
    """Level 1: does the XML parse at all."""
    try:
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if n.endswith(('.xml', '.rels')):
                    etree.fromstring(z.read(n))
        return True
    except Exception:
        return False


def schema_ok(path):
    """Level 2: approximation of schema validation.

    The full ECMA-376 XSDs are not bundled here, so this checks what the
    schema checks: namespace correctness and admissible root elements. For
    these mutations it yields the same verdict a real XSD would - every one
    is schema-legal, because they break REFERENTIAL integrity, not grammar.
    Swap in a real validator before publishing numbers.
    """
    W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    try:
        with zipfile.ZipFile(path) as z:
            doc = etree.fromstring(z.read('word/document.xml'))
        if doc.tag != f'{{{W}}}document':
            return False
        if doc.find(f'{{{W}}}body') is None:
            return False
        return True
    except Exception:
        return False


def renders(path):
    """Level 3: does it convert to PDF (proxy for "it looks fine")."""
    d = '/tmp/cmp'
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)
    subprocess.run(['soffice', '--headless', '--convert-to', 'pdf', '--outdir', d, path],
                   capture_output=True, timeout=180)
    pdf = os.path.join(d, os.path.basename(path).replace('.docx', '.pdf'))
    return os.path.exists(pdf) and os.path.getsize(pdf) > 1000


def main():
    rows = []
    for key, desc, fn in MUTATORS:
        p = f'{OUT}/{key}.docx'
        if not os.path.exists(p):
            continue
        ins = [f for f in inspect(p) if f.severity in (ERROR, WARN)]
        fid = compare(BASE, p)
        rows.append({
            'key': key, 'desc': desc,
            'wf': wellformed(p),
            'schema': schema_ok(p),
            'render': renders(p),
            'insp': len(ins),
            'fid': len(fid),
            'fid_items': fid,
            'insp_items': ins,
        })

    print('=' * 104)
    print('WHAT EACH APPROACH CATCHES  (ok = "no problem found", i.e. defect MISSED)')
    print('=' * 104)
    print(f'{"defect introduced by the agent":<40}{"well-":<8}{"schema":<8}{"render":<9}'
          f'{"inspector":<12}{"fidelity":<12}')
    print(f'{"":<40}{"formed":<8}{"":<8}{"(LO)":<9}{"":<12}{"vs source":<12}')
    print('-' * 104)

    missed_by_render = 0
    caught_by_ours = 0
    for r in rows:
        wf = 'ok' if r['wf'] else 'FAIL'
        sc = 'ok' if r['schema'] else 'FAIL'
        rd = 'ok' if r['render'] else 'FAIL'
        ins = f'{r["insp"]} found' if r['insp'] else 'ok'
        fd = f'{r["fid"]} losses' if r['fid'] else 'ok'
        print(f'{r["desc"][:39]:<40}{wf:<8}{sc:<8}{rd:<9}{ins:<12}{fd:<12}')
        real_defect = r['key'] != 'A_roundtrip' and r['key'] != 'C1_value'
        if real_defect:
            if r['render']:
                missed_by_render += 1
            if r['insp'] or r['fid']:
                caught_by_ours += 1

    print('=' * 104)
    total_defects = sum(1 for r in rows if r['key'] not in ('A_roundtrip', 'C1_value'))
    print(f'\nReal defects introduced: {total_defects}')
    print(f'  missed by well-formed check:  {sum(1 for r in rows if r["wf"] and r["key"] not in ("A_roundtrip","C1_value"))}/{total_defects}')
    print(f'  missed by schema validation:  {sum(1 for r in rows if r["schema"] and r["key"] not in ("A_roundtrip","C1_value"))}/{total_defects}')
    print(f'  missed by PDF rendering:      {missed_by_render}/{total_defects}')
    print(f'  caught by this prototype:     {caught_by_ours}/{total_defects}')

    print('\n\nWHAT THE FIDELITY CHECK SEES\n')
    for r in rows:
        if not r['fid_items']:
            continue
        print(f'--- {r["desc"]}')
        for f in r['fid_items']:
            print(f'    [{f.severity.value.upper():5}] {f.code}  {f.message}')
        print()


if __name__ == '__main__':
    main()
