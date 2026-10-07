# Prototypes from the research phase

- `arnorm.py` — two-layer Arabic normalizer tested during research (2026-10-06):
  - `canonical()` → stored/displayed text (NFKC, strip bidi controls, Persian letters → Arabic, digits → ASCII)
  - `search_key()` → lossy search/dedup key (tashkeel/tatweel removed, أ/إ/آ→ا, ى→ي, ة→ه)
  Verified: presentation forms, tashkeel/tatweel and Persian-letter variants of "الإرشاد الطلابي" all map to the same key.
  It is ported to `packages/core/arabic` (TypeScript) and `services/ingest` (Python) in Phase 1, with shared test vectors so both produce identical keys.

## `tests/` — scripts behind the "تجربة أولية" claims in docs/06 and docs/07

Run during research on 2026-10-06 (PostgreSQL 16.15, PyMuPDF 1.28.2, pdfplumber 0.11.10, Tesseract 5.3.4, LibreOffice 24.2). Inputs were small synthetic samples, so the results are indicative only and are re-run on the real corpus in Phase 2.

- `mk.py` — builds the samples: an Arabic RTL DOCX, and a visual-order PDF made with arabic_reshaper + python-bidi.
- `ex.py` — compares PyMuPDF (default / sort=True), pdfplumber, mammoth and python-docx on those samples (logical vs reversed order, presentation forms, لا→ال corruption).
- `ocr.py` — Tesseract ara / ara+eng at 150/300 dpi, character error rate against the ground truth.
- `dedup.py` — pg_trgm similarity (raw vs normalized) and MinHash on six stem pairs (paraphrase, negation flip, title rename…).
