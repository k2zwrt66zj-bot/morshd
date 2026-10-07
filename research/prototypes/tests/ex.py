import sys, unicodedata, pymupdf, pdfplumber, mammoth, re
def pf(s): return sum(1 for ch in s if 0xFB50<=ord(ch)<=0xFDFF or 0xFE70<=ord(ch)<=0xFEFF)
for pdf in sys.argv[1:3]:
    print("=====",pdf.split('/')[-1])
    doc=pymupdf.open(pdf)
    t=doc[0].get_text()
    print("pymupdf default:", repr(t[:200]), "presforms=",pf(t))
    t2=doc[0].get_text(sort=True)
    print("pymupdf sort:", repr(t2[:120]))
    with pdfplumber.open(pdf) as p:
        t3=p.pages[0].extract_text() or ''
    print("pdfplumber:", repr(t3[:200]), "presforms=",pf(t3))
    n=unicodedata.normalize('NFKC',t)
    print("pymupdf+NFKC:", repr(n[:120]))
with open(sys.argv[3],'rb') as f:
    r=mammoth.extract_raw_text(f)
print("mammoth raw:", repr(r.value[:200]))
from docx import Document
print("python-docx:", [p.text for p in Document(sys.argv[3]).paragraphs][:2])
