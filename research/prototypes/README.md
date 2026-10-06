# Prototypes from the research phase

- `arnorm.py` — two-layer Arabic normalizer tested during research (2026-10-06):
  - `canonical()` → stored/displayed text (NFKC, strip bidi controls, Persian letters → Arabic, digits → ASCII)
  - `search_key()` → lossy search/dedup key (tashkeel/tatweel removed, أ/إ/آ→ا, ى→ي, ة→ه)
  Verified: presentation forms, tashkeel/tatweel and Persian-letter variants of "الإرشاد الطلابي" all map to the same key.
  It is ported to `packages/core/arabic` (TypeScript) and `services/ingest` (Python) in Phase 1, with shared test vectors so both produce identical keys.
