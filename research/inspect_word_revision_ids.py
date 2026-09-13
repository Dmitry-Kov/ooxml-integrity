#!/usr/bin/env python3
"""Read-only analysis of the three frozen Word BND-001 observations.

This is a focused review ledger, not a replacement semantic-diff/oracle profile.
Original oracle residuals and package differences remain visible in the report.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from lxml import etree as E

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research import docx_benchmark as b
from research import revision_evidence as r

BASE = ROOT / 'evidence/docx-word-id-followup'
UTC_ATTR = '{http://schemas.microsoft.com/office/word/2023/wordml/word16du}dateUtc'


def toggled(node, name):
    prop = node.find('w:rPr/w:' + name, r.NS)
    if prop is None:
        return None
    return prop.get(r.W + 'val', '1') not in ('0', 'false', 'off')


def review_characters(parts):
    """Per-character review payload, author, effective UTC and paragraph position.

    Group fragmentation/IDs are deliberately exposed separately. The effective
    UTC uses dateUtc when present; both raw timestamps stay in revision_nodes.
    These basic fixtures have no nested revisions, moves or property changes.
    """
    result = []
    for part, data in sorted(parts.items()):
        if not part.startswith('word/') or not part.endswith('.xml'):
            continue
        root = E.fromstring(data)
        for position, p in enumerate(root.iter(r.W + 'p')):
            for t in p.iter():
                if t.tag not in (r.W + 't', r.W + 'delText'):
                    continue
                lineage = [n for n in t.iterancestors() if n.tag in (r.W+'ins',r.W+'del')]
                if not lineage:
                    continue
                context = tuple((E.QName(n).localname, n.get(r.W+'author'),
                                 n.get(UTC_ATTR, n.get(r.W+'date'))) for n in lineage)
                run = t.getparent()
                formatting = (toggled(run, 'b'), toggled(run, 'i'))
                result.extend((part,position,context,formatting,char) for char in (t.text or ''))
    return result


def revision_nodes(parts):
    result = []
    for part, data in sorted(parts.items()):
        if not part.startswith('word/') or not part.endswith('.xml'):
            continue
        for node in E.fromstring(data).iter():
            if node.tag not in (r.W+'ins',r.W+'del'):
                continue
            result.append({'part':part,'kind':E.QName(node).localname,'id':node.get(r.W+'id'),
                           'author':node.get(r.W+'author'),'date':node.get(r.W+'date'),
                           'dateUtc':node.get(UTC_ATTR),
                           'text':''.join(t.text or '' for t in node.iter() if t.tag in (r.W+'t',r.W+'delText'))})
    return result


def anchors(parts):
    definitions = {}
    for kind,part in (('comment','word/comments.xml'),('footnote','word/footnotes.xml')):
        if part in parts:
            definitions[kind]={node.get(r.W+'id'):''.join(t.text or '' for t in node.iter(r.W+'t'))
                               for node in E.fromstring(parts[part]).iter(r.W+kind)}
    result=[]
    for position,p in enumerate(E.fromstring(parts[r.MAIN]).iter(r.W+'p')):
        offset=0
        for node in p.iter():
            name=E.QName(node).localname
            if name in ('commentRangeStart','commentRangeEnd','commentReference','footnoteReference'):
                kind='footnote' if name=='footnoteReference' else 'comment'
                result.append((position,offset,name,definitions[kind].get(node.get(r.W+'id'),'MISSING_DEFINITION')))
            if node.tag==r.W+'t' and not any(a.tag==r.W+'del' for a in node.iterancestors()):
                offset+=len(node.text or '')
    return result


def target_formats(parts):
    p=E.fromstring(parts[r.MAIN]).findall('w:body/w:p',r.NS)[2]
    result=[]
    for t in p.iter(r.W+'t'):
        if any(a.tag==r.W+'del' for a in t.iterancestors()):
            continue
        result.extend((char,toggled(t.getparent(),'b'),toggled(t.getparent(),'i')) for char in (t.text or ''))
    return result


def relationships(parts):
    result=[]
    for name,blob in sorted(parts.items()):
        if name.endswith('.rels'):
            result.extend((name,node.get('Type'),node.get('Target'),node.get('TargetMode','Internal'))
                          for node in E.fromstring(blob))
    return Counter(result)


def compare(source, output, ident):
    before,after=r.read(source),r.read(output)
    case={'id':ident,'action':'save','cohort':'word_followup','allowed_text_changes':[],
          'allowed_revision_losses':[],'comparison_profile':r.WORD_SAVE_PROFILE}
    oracle=r.oracle(before,after,case)
    a,z=review_characters(before),review_characters(after)
    old_rels,new_rels=relationships(before),relationships(after)
    old_parts,_=b.package_facts(before,'save')
    new_parts,_=b.package_facts(after,'save')
    return {'input_sha256':b.digest(source),'output_sha256':b.digest(output),
            'original_oracle_unmodified':oracle,
            'current_text_preserved':r.facts(before,True)['text']==r.facts(after,True)['text'],
            'review_characters_authors_utc_positions_direct_bold_italic_preserved':a==z,
            'review_character_count':[len(a),len(z)],
            'review_character_sha256':[r.digest(b.json_bytes(a)),r.digest(b.json_bytes(z))],
            'target_current_text_and_direct_bold_italic_preserved':target_formats(before)==target_formats(after),
            'anchors_and_note_references_at_same_text_positions':anchors(before)==anchors(after),
            'anchors_before':anchors(before),'anchors_after':anchors(after),
            'revision_nodes_before':revision_nodes(before),'revision_nodes_after':revision_nodes(after),
            'raw_duplicate_ids_before':r.facts(before)['duplicates'],'raw_duplicate_ids_after':r.facts(after)['duplicates'],
            'removed_parts':sorted(set(before)-set(after)),'added_parts':sorted(set(after)-set(before)),
            'changed_parts':[p for p in sorted(set(before)&set(after)) if before[p]!=after[p]],
            'normalized_package_differences':[p for p in sorted(set(old_parts)|set(new_parts)) if old_parts.get(p)!=new_parts.get(p)],
            'removed_relationships':list((old_rels-new_rels).elements()),'added_relationships':list((new_rels-old_rels).elements()),
            'checker_before':b.checker_findings(source,source),'checker_after':b.checker_findings(source,output),
            'raw_part_hashes_after':{p:r.digest(blob) for p,blob in after.items()}}


def evaluate():
    declaration=json.loads((BASE/'declaration.json').read_text())
    capture=json.loads((BASE/'capture.json').read_text())
    if capture['declaration_sha256']!=b.digest(BASE/'declaration.json') or declaration['protocol_sha256']!=b.digest(BASE/'PROTOCOL.md'):
        raise ValueError('Declaration drift')
    if declaration['checker_source_sha256']!=b.tree_hash(ROOT/'src/ooxml_integrity'):
        raise ValueError('Checker drift')
    declared={c['id']:c for c in declaration['inputs']}
    if len(capture['cases'])!=3 or {c['id'] for c in capture['cases']}!=set(declared):
        raise ValueError('Inventory drift')
    results=[]
    for record in capture['cases']:
        if any(record.get(k)!=v for k,v in declared[record['id']].items()):
            raise ValueError('Input declaration drift')
        source,output=ROOT/record['path'],ROOT/record['output']
        if b.digest(source)!=record['sha256'] or b.digest(output)!=record['output_sha256']:
            raise ValueError('File drift')
        results.append({'id':record['id'],'cohort':record['cohort'],**compare(source,output,record['id'])})
    return {'capture_sha256':b.digest(BASE/'capture.json'),'analysis_source_sha256':b.digest(__file__),
            'analysis_scope':'Diagnostic comparison after capture, no new pass profile or score changes',
            'cases':results}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--write',action='store_true')
    args=p.parse_args()
    result=json.loads(b.json_bytes(evaluate()))
    if args.write:
        b.save_json(BASE/'evaluation.json',result)
    elif result!=json.loads((BASE/'evaluation.json').read_text()):
        raise ValueError('Evaluation drift')
    for c in result['cases']:
        print(c['id'], 'review characters preserved:',c['review_characters_authors_utc_positions_direct_bold_italic_preserved'],
              'target formats:',c['target_current_text_and_direct_bold_italic_preserved'],
              'anchors:',c['anchors_and_note_references_at_same_text_positions'],
              'removed parts:',c['removed_parts'])


if __name__=='__main__':
    main()
