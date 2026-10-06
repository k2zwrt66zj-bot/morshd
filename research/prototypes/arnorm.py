import re, unicodedata

# Layer 1: canonical form (store this; safe to display)
_INVISIBLE = dict.fromkeys(
    [0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x061C, 0x202A, 0x202B, 0x202C,
     0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069, 0xFEFF, 0x00AD], None)
_FA2AR = {0x06CC: 0x064A,  # Farsi yeh -> Arabic yeh
          0x06D2: 0x064A,  # yeh barree -> yeh
          0x06A9: 0x0643,  # keheh -> kaf
          0x06BE: 0x0647,  # heh doachashmee -> heh
          0x06C1: 0x0647,  # heh goal -> heh
          0x06D5: 0x0647,  # ae -> heh
          0x06C0: 0x0647,  # heh with yeh above -> heh
          0x0671: 0x0627,  # alef wasla -> alef
          0x066B: ord('.'), 0x066C: ord(','), 0x066A: ord('%')}
_FA2AR.update({0x0660 + i: ord(str(i)) for i in range(10)})  # Arabic-Indic digits
_FA2AR.update({0x06F0 + i: ord(str(i)) for i in range(10)})  # Extended (Persian) digits


def canonical(s: str) -> str:
    s = unicodedata.normalize('NFKC', s)       # presentation forms / ligatures -> base letters
    s = s.translate(_INVISIBLE).translate(_FA2AR)
    s = re.sub(r'[ \t  - 　]+', ' ', s)
    return s.strip()


# Layer 2: search / dedup key (lossy; never displayed)
_TASHKEEL = re.compile('[ؐ-ًؚ-ٰٟۖ-ۭـ]')  # harakat, dagger alef, Quranic marks, tatweel
_KEY = {0x0623: 0x0627, 0x0625: 0x0627, 0x0622: 0x0627,  # hamzated alefs -> bare alef
        0x0649: 0x064A,                                  # alef maqsura -> yeh
        0x0629: 0x0647}                                  # ta marbuta -> heh


def search_key(s: str) -> str:
    s = _TASHKEEL.sub('', canonical(s)).translate(_KEY).casefold()
    s = re.sub(r'[^\w\s]', ' ', s)                       # punctuation incl. Arabic comma/semicolon/question mark
    return re.sub(r'\s+', ' ', s).strip()


if __name__ == '__main__':
    tests = ['ﺍﻹﺭﺷﺎﺩ ﺍﻟﻄﻼﺑﻲ',
             'الإرشـــاد الطُّلابيُّ', 'الارشاد الطلابی', 'مستشفى ٢٠٢٤',
             '‫ما هو دور المرشد؟‬', 'مدرسة', 'کتاب ھذا']
    for t in tests:
        print(repr(t), '->', repr(canonical(t)), '->', repr(search_key(t)))
