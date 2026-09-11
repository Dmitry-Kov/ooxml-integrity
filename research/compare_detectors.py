#!/usr/bin/env python3
"""
Controlled mutation comparison: the checks actually performed.

  1. well-formed XML   - what any parser does
  2. root/body check   - expected Word namespace, document root and body
  3. PDF creation      - LibreOffice produced a PDF larger than 1000 bytes
  4. structural inspector + fidelity check against the source (this prototype)

No full XSD validation, systematic visual review or neighbouring tool workflow
is measured by this script. The inputs are hand-written mutations, not agent runs.
"""
import os, subprocess, tempfile, zipfile
from pathlib import Path
from lxml import etree
from ooxml_integrity import check as inspect, ERROR, WARN
from ooxml_integrity import compare
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


def root_body_ok(path):
    """Expected main-document namespace, root and body; not XSD validation."""
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


def pdf_created(path):
    """Only PDF creation is checked; no pages are inspected or scored."""
    with tempfile.TemporaryDirectory(prefix='ooxml-detectors-') as directory:
        profile = (Path(directory) / 'profile').as_uri()
        subprocess.run(['soffice', f'-env:UserInstallation={profile}', '--headless',
                        '--convert-to', 'pdf', '--outdir', directory, path],
                       capture_output=True, timeout=180)
        pdf = Path(directory) / (Path(path).stem + '.pdf')
        return pdf.exists() and pdf.stat().st_size > 1000


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
            'root': root_body_ok(p),
            'pdf': pdf_created(p),
            'insp': len(ins),
            'fid': len(fid),
            'fid_items': fid,
            'insp_items': ins,
        })

    print('=' * 104)
    print('CONTROLLED MUTATIONS  (yes = this step succeeded, not a clean-document verdict)')
    print('=' * 104)
    print(f'{"controlled edit":<40}{"XML":<8}{"root/":<8}{"PDF":<9}'
          f'{"inspector":<12}{"fidelity":<12}')
    print(f'{"":<40}{"parses":<8}{"body":<8}{"created":<9}{"":<12}{"vs source":<12}')
    print('-' * 104)

    pdf_successes = 0
    caught_by_ours = 0
    for r in rows:
        wf = 'yes' if r['wf'] else 'FAIL'
        sc = 'yes' if r['root'] else 'FAIL'
        rd = 'yes' if r['pdf'] else 'FAIL'
        ins = f'{r["insp"]} found' if r['insp'] else 'ok'
        fd = f'{r["fid"]} reports' if r['fid'] else 'ok'
        print(f'{r["desc"][:39]:<40}{wf:<8}{sc:<8}{rd:<9}{ins:<12}{fd:<12}')
        real_defect = r['key'] != 'A_roundtrip' and r['key'] != 'C1_value'
        if real_defect:
            if r['pdf']:
                pdf_successes += 1
            if r['insp'] or any(f.severity in (ERROR, WARN) for f in r['fid_items']):
                caught_by_ours += 1

    print('=' * 104)
    total_defects = sum(1 for r in rows if r['key'] not in ('A_roundtrip', 'C1_value'))
    print(f'\nControlled defect cases: {total_defects}')
    print(f'  XML parsing succeeded:       {sum(1 for r in rows if r["wf"] and r["key"] not in ("A_roundtrip","C1_value"))}/{total_defects}')
    print(f'  root/body check passed:      {sum(1 for r in rows if r["root"] and r["key"] not in ("A_roundtrip","C1_value"))}/{total_defects}')
    print(f'  PDF creation succeeded:      {pdf_successes}/{total_defects}')
    print(f'  checker reported findings:   {caught_by_ours}/{total_defects}')
    print('Full XSD validation and systematic visual review: not measured.')
    print('Fidelity reports include INFO additions; see severities below.')

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
