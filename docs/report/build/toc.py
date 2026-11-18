import subprocess,zipfile,re,os,shutil,sys
from xml.sax.saxutils import escape
heads=[(1,"1. INTRODUCTION"),(2,"1.1 Background"),(2,"1.2 Problem Statement"),(1,"2. LITERATURE SURVEY"),
(2,"2.1 Mapping floods with radar"),(2,"2.2 False water and uncertainty"),(2,"2.3 Paddy and flooded paddy in India"),(2,"2.4 Official systems"),(2,"2.5 Turning maps into trustworthy area numbers"),(2,"2.6 Summary and research gap"),
(1,"3. DESIGN AND METHODOLOGY"),(2,"3.1 The idea in one picture"),(2,"3.2 Layer 1: Map (the quick guess)"),(2,"3.3 Layer 2: Check (the research contribution)"),(2,"3.4 Layer 3: Tool (what the officer sees)"),(2,"3.5 Why this is novel, and what we learn"),(2,"3.6 Evaluation plan"),(2,"3.7 Progress and plan to the Final Review"),(1,"REFERENCES")]
src=sys.argv[1]; pdf=sys.argv[2]; out=sys.argv[3]
n=int(re.search(r'Pages:\s+(\d+)',subprocess.run(['pdfinfo',pdf],capture_output=True,text=True).stdout).group(1))
pages=[subprocess.run(['pdftotext','-f',str(i),'-l',str(i),'-layout',pdf,'-'],capture_output=True,text=True).stdout for i in range(1,n+1)]
res=[];start=2  # 0-based index of first body page (cover=0, toc=1)
for lvl,h in heads:
    found=None
    for i in range(start,n):
        if any(l.strip()==h or l.strip().startswith(h) for l in pages[i].splitlines()): found=i;break
    assert found is not None,h
    start=found; res.append((lvl,h,found-1))   # arabic page = idx-1
tmp='tocx'; shutil.rmtree(tmp,ignore_errors=True)
zipfile.ZipFile(src).extractall(tmp)
d=open(tmp+'/word/document.xml').read()
ents=[]
for k,(lvl,h,p) in enumerate(res):
    pre=''
    if k==0: pre='<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> TOC \\o "1-2" \\h \\z \\u </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r>'
    post='<w:r><w:fldChar w:fldCharType="end"/></w:r>' if k==len(res)-1 else ''
    ents.append(f'<w:p><w:pPr><w:pStyle w:val="TOC{lvl}"/><w:tabs><w:tab w:val="right" w:leader="dot" w:pos="8651"/></w:tabs></w:pPr>{pre}<w:r><w:t xml:space="preserve">{escape(h)}</w:t></w:r><w:r><w:tab/></w:r><w:r><w:t>{p}</w:t></w:r>{post}</w:p>')
i=d.find('<w:sdtContent>')+len('<w:sdtContent>'); j=d.find('</w:sdtContent>')
d=d[:i]+''.join(ents)+d[j:]
open(tmp+'/word/document.xml','w').write(d)
if os.path.exists(out): os.remove(out)
subprocess.run(f'cd {tmp} && zip -XrD ../{out} "[Content_Types].xml" _rels docProps word >/dev/null',shell=True,check=True)
print(res)
