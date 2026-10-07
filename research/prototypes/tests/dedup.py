import sys, json, subprocess
sys.path.insert(0, sys.argv[1])
from arnorm import search_key
from datasketch import MinHash
pairs = [
 ("exact+tashkeel+presforms", "ما الهدف الرئيس من التوجيه الطلابي في المدرسة؟", "ﻣﺎ ﺍﻟﻬﺪﻑ ﺍﻟﺮﺋﻴﺲ ﻣﻦ ﺍﻟﺘﻮﺟﻴﻪ ﺍﻟﻄُّﻼﺑﻲ ﻓﻲ ﺍﻟﻤﺪﺭﺳﺔ؟"),
 ("minor paraphrase", "ما الهدف الرئيس من التوجيه الطلابي في المدرسة؟", "ما الهدف الأساسي للتوجيه الطلابي في المدارس؟"),
 ("word-order change", "يهدف التوجيه الطلابي في المدرسة إلى تنمية شخصية الطالب", "تنمية شخصية الطالب هي هدف التوجيه الطلابي في المدرسة"),
 ("NEGATION flip", "أي مما يلي يُعد من مهام الموجه الطلابي؟", "أي مما يلي لا يُعد من مهام الموجه الطلابي؟"),
 ("same topic, diff question", "ما الهدف الرئيس من التوجيه الطلابي في المدرسة؟", "ما دور المرشد الطلابي في معالجة التأخر الدراسي؟"),
 ("old vs new title", "من مهام المرشد الطلابي دراسة حالات الطلاب المتأخرين دراسيا", "من مهام الموجه الطلابي دراسة حالات الطلاب المتأخرين دراسياً"),
]
def mh(tokens):
    m=MinHash(num_perm=128, seed=1)
    for t in tokens: m.update(t.encode())
    return m
def shingles_words(s,k=2):
    w=s.split(); return {' '.join(w[i:i+k]) for i in range(max(1,len(w)-k+1))}
def shingles_chars(s,k=4):
    s=s.replace(' ','_'); return {s[i:i+k] for i in range(max(1,len(s)-k+1))}
rows=[]
for name,a,b in pairs:
    ka,kb=search_key(a),search_key(b)
    sql=f"select round(similarity($${ka}$$,$${kb}$$)::numeric,3), round(similarity($${a}$$,$${b}$$)::numeric,3)"
    out=subprocess.run(['psql','-h','127.0.0.1','-p','54329','-U','postgres','-At','-c',sql],capture_output=True,text=True).stdout.strip()
    jw=mh(shingles_words(ka)).jaccard(mh(shingles_words(kb)))
    jc=mh(shingles_chars(ka)).jaccard(mh(shingles_chars(kb)))
    print(f"{name:26s} trgm(norm)|trgm(raw)={out}  minhash word2={jw:.2f} char4={jc:.2f}")
