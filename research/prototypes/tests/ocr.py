import sys, subprocess, pymupdf, unicodedata
from rapidfuzz.distance import Levenshtein
pdf, outdir, best = sys.argv[1], sys.argv[2], sys.argv[3]
truth = ["السؤال ١: ما الهدف الرئيس من التوجيه الطلابي في المدرسة؟",
 "أ) تنمية شخصية الطالب في الجوانب النفسية والاجتماعية عام 2024",
 "ب) إعداد الجداول الدراسية (Schedules) للمعلمين"]
gt=" ".join(" ".join(truth).split())
d=pymupdf.open(pdf)
for dpi in (150,300):
    png=f"{outdir}/p{dpi}.png"; d[0].get_pixmap(dpi=dpi).save(png)
    for name,args in (("fast(apt)",[]),("best",["--tessdata-dir",best])):
        for lang in ("ara","ara+eng"):
            out=subprocess.run(["tesseract",png,"-","-l",lang,"--psm","6"]+args,capture_output=True,text=True).stdout
            o=" ".join(out.split())
            cer=Levenshtein.distance(o,gt)/len(gt)
            print(f"dpi={dpi} {name} {lang}: CER={cer:.3f} | {o[:160]}")
