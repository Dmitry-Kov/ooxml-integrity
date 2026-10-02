import zipfile
src='/work/input.docx'; dst='/work/output.docx'
zin=zipfile.ZipFile(src); files={n:zin.read(n) for n in zin.namelist()}
W14='http://schemas.microsoft.com/office/word/2010/wordml'
D='2026-10-02T00:00:00Z'
c=files['word/comments.xml'].decode()
c=c.replace('<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">',
 f'<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:w14="{W14}">',1)
c=c.replace('<w:p><w:r><w:t>Confirm this figure','<w:p w14:paraId="1A000001" w14:textId="77777777"><w:r><w:t>Confirm this figure',1)
c=c.replace('<w:p><w:r><w:t>Defined term','<w:p w14:paraId="1A000002" w14:textId="77777777"><w:r><w:t>Defined term',1)
new=(f'<w:comment w:id="3" w:author="Benchmark Editor" w:initials="BE" w:date="{D}">\n'
 '<w:p w14:paraId="1A000003" w14:textId="77777777"><w:r><w:t>Checked against the definitions schedule.</w:t></w:r></w:p></w:comment>\n'
 f'<w:comment w:id="4" w:author="Benchmark Editor" w:initials="BE" w:date="{D}">\n'
 '<w:p w14:paraId="1A000004" w14:textId="77777777"><w:r><w:t>Confirm the payment term with finance.</w:t></w:r></w:p></w:comment>\n')
assert c.count('</w:comments>')==1
c=c.replace('</w:comments>',new+'</w:comments>')
files['word/comments.xml']=c.encode()
files['word/commentsExtended.xml']=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
 '<w15:commentsEx xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml">'
 '<w15:commentEx w15:paraId="1A000001" w15:done="0"/>'
 '<w15:commentEx w15:paraId="1A000002" w15:done="0"/>'
 '<w15:commentEx w15:paraId="1A000003" w15:paraIdParent="1A000002" w15:done="0"/>'
 '<w15:commentEx w15:paraId="1A000004" w15:done="0"/>'
 '</w15:commentsEx>').encode()
ct=files['[Content_Types].xml'].decode()
ct=ct.replace('</Types>','<Override PartName="/word/commentsExtended.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.commentsExtended+xml"/>\n</Types>')
files['[Content_Types].xml']=ct.encode()
r=files['word/_rels/document.xml.rels'].decode()
r=r.replace('</Relationships>','<Relationship Id="rId10" Type="http://schemas.microsoft.com/office/2011/relationships/commentsExtended" Target="commentsExtended.xml"/>\n</Relationships>')
files['word/_rels/document.xml.rels']=r.encode()
d=files['word/document.xml'].decode()
def rep(a,b):
    global d; assert d.count(a)==1,a; d=d.replace(a,b)
rep('<w:commentRangeStart w:id="2"/>','<w:commentRangeStart w:id="2"/><w:commentRangeStart w:id="3"/>')
rep('<w:commentRangeEnd w:id="2"/>','<w:commentRangeEnd w:id="2"/><w:commentRangeEnd w:id="3"/>')
rep('<w:r><w:commentReference w:id="2"/></w:r>','<w:r><w:commentReference w:id="2"/></w:r><w:r><w:commentReference w:id="3"/></w:r>')
rep('<w:r><w:t>Invoices are payable within 30 days.</w:t></w:r>',
 '<w:r><w:t xml:space="preserve">Invoices are payable within </w:t></w:r><w:commentRangeStart w:id="4"/><w:r><w:t>30 days</w:t></w:r><w:commentRangeEnd w:id="4"/><w:r><w:commentReference w:id="4"/></w:r><w:r><w:t>.</w:t></w:r>')
files['word/document.xml']=d.encode()
with zipfile.ZipFile(dst,'w',zipfile.ZIP_DEFLATED) as z:
    for i in zin.infolist():
        z.writestr(i,files[i.filename])
    z.writestr('word/commentsExtended.xml',files['word/commentsExtended.xml'])
