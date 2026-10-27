"""Name / text normalisation for Indian-language input.

- `romanize`: Devanagari and Gujarati script → rough Latin transliteration (what a speech engine emits for
  hi-IN / gu-IN is usually native script, while shopkeepers type Latin).
- `canon`: light folding used for keyword and alias equality (vowel length, w/v, doubled letters).
- `phonetic_key`: heavier folding for fuzzy name matching (drops aspiration, vowels after the first letter).
- `similarity`: Jaro-Winkler on canonical forms, with a phonetic-key bonus.
- `strip_honorifics`: bhai / ben / ji / Shri / Smt ... as separate tokens or glued suffixes.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

# ---------------------------------------------------------------- romanisation
# Devanagari block U+0900–U+097F. Gujarati (U+0A80–U+0AFF) is laid out in parallel (+0x180), so Gujarati is
# mapped onto Devanagari first and shares the table.
_VOWELS = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri", "ए": "e", "ऐ": "ai",
    "ओ": "o", "औ": "au", "ऍ": "e", "ऑ": "o", "ऎ": "e", "ऒ": "o",
}
_MATRAS = {
    "ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
    "ॅ": "e", "ॉ": "o", "ॆ": "e", "ॊ": "o",
}
_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "ळ": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h", "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "r", "ढ़": "rh",
    "फ़": "f", "य़": "y",
}
_SIGNS = {"ं": "n", "ँ": "n", "ः": "h", "़": "", "्": "", "ऽ": "", "।": ".", "॥": "."}
_DIGITS = {chr(0x0966 + i): str(i) for i in range(10)} | {chr(0x0AE6 + i): str(i) for i in range(10)}
_INDIC_RE = re.compile(r"[ऀ-ॿ઀-૿]")


def _guj_to_deva(ch: str) -> str:
    cp = ord(ch)
    return chr(cp - 0x180) if 0x0A80 <= cp <= 0x0AFF and not 0x0AE6 <= cp <= 0x0AEF else ch


def has_indic_script(text: str) -> bool:
    return bool(_INDIC_RE.search(text))


def _romanize_word(word: str) -> str:
    out: list[str] = []
    chars = [_guj_to_deva(c) for c in unicodedata.normalize("NFC", word)]
    i = 0
    while i < len(chars):
        c = chars[i]
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        if c in _CONSONANTS:
            # nukta forms
            if nxt == "़" and (c + nxt) in _CONSONANTS:
                out.append(_CONSONANTS[c + nxt])
                i += 2
                nxt = chars[i] if i < len(chars) else ""
            else:
                out.append(_CONSONANTS[c])
                i += 1
            if nxt in _MATRAS:
                out.append(_MATRAS[nxt])
                i += 1
            elif nxt == "्":
                i += 1
            else:
                out.append("a")  # inherent vowel; final one is dropped below (schwa deletion)
            continue
        if c in _VOWELS:
            out.append(_VOWELS[c])
        elif c in _SIGNS:
            out.append(_SIGNS[c])
        elif c in _DIGITS:
            out.append(_DIGITS[c])
        else:
            out.append(c)
        i += 1
    s = "".join(out)
    # schwa deletion: drop a word-final inherent 'a' on multi-syllable words (रमेश → ramesh, not ramesha)
    if len(s) > 2 and s.endswith("a") and not s.endswith("aa") and chars and chars[-1] in _CONSONANTS:
        s = s[:-1]
    return s


def romanize(text: str) -> str:
    """Transliterate any Devanagari/Gujarati runs in `text` to Latin; Latin text passes through."""
    if not has_indic_script(text):
        return text
    return re.sub(r"[ऀ-ॿ઀-૿]+", lambda m: _romanize_word(m.group(0)), text)


# ---------------------------------------------------------------- folding
_CANON_SUBS = [
    (re.compile(r"w"), "v"),
    (re.compile(r"ph"), "f"),
    (re.compile(r"z"), "j"),
    (re.compile(r"q"), "k"),
    (re.compile(r"ck"), "k"),
    (re.compile(r"c(?!h)"), "k"),
    (re.compile(r"ee|ii|ie$"), "i"),
    (re.compile(r"oo|uu"), "u"),
    (re.compile(r"aa"), "a"),
    (re.compile(r"ou"), "au"),
    (re.compile(r"y$"), "i"),
    (re.compile(r"(.)\1+"), r"\1"),
]


@lru_cache(maxsize=20000)
def canon(word: str) -> str:
    """Light canonical form: 'Chaawal' → 'chaval', 'udhaar' → 'udhar', 'Parle-G' → 'parleg'."""
    w = romanize(word).lower()
    w = re.sub(r"[^a-z0-9]", "", w)
    for pat, rep in _CANON_SUBS:
        w = pat.sub(rep, w)
    return w


@lru_cache(maxsize=20000)
def phonetic_key(word: str) -> str:
    """Heavier key for names: drops aspiration and non-initial vowels. 'Kishore'/'Kishor'/'Kisor' → 'ksr'."""
    w = canon(word)
    if not w:
        return ""
    w = re.sub(r"([kgcjtdpbs])h", r"\1", w)  # aspirated → plain (bh→b, sh→s, chh→c)
    w = w.replace("v", "b") if w.startswith("v") else w
    head, tail = w[0], re.sub(r"[aeiouy]", "", w[1:])
    return re.sub(r"(.)\1+", r"\1", head + tail)


def canon_phrase(text: str) -> str:
    return " ".join(canon(t) for t in tokenize(text) if canon(t))


def tokenize(text: str) -> list[str]:
    text = romanize(text)
    text = text.replace("₹", " ₹ ")
    return re.findall(r"₹|\d+(?:[.,]\d+)?|[^\W\d_]+(?:-[^\W\d_]+)*", text.lower())


# ---------------------------------------------------------------- similarity
def jaro_winkler(a: str, b: str, p: float = 0.1) -> float:
    if a == b:
        return 1.0
    la, lb = len(a), len(b)
    if not la or not lb:
        return 0.0
    window = max(la, lb) // 2 - 1
    a_match, b_match = [False] * la, [False] * lb
    matches = 0
    for i, ca in enumerate(a):
        lo, hi = max(0, i - window), min(lb, i + window + 1)
        for j in range(lo, hi):
            if not b_match[j] and b[j] == ca:
                a_match[i] = b_match[j] = True
                matches += 1
                break
    if not matches:
        return 0.0
    transpositions, k = 0, 0
    for i in range(la):
        if a_match[i]:
            while not b_match[k]:
                k += 1
            if a[i] != b[k]:
                transpositions += 1
            k += 1
    m = float(matches)
    jaro = (m / la + m / lb + (m - transpositions / 2) / m) / 3
    prefix = 0
    for ca, cb in zip(a[:4], b[:4], strict=False):
        if ca != cb:
            break
        prefix += 1
    return jaro + prefix * p * (1 - jaro)


def similarity(a: str, b: str, phonetic_floor: bool = True) -> float:
    """0..1 similarity between two words/phrases using canonical forms.

    Names get a phonetic-equality floor (Kishore ≈ Kisor); products only a small bonus, because short
    product words share skeletons too easily (cheeni/chana both reduce to 'cn').
    """
    ca, cb = canon_phrase(a), canon_phrase(b)
    if not ca or not cb:
        return 0.0
    if ca == cb:
        return 1.0
    score = jaro_winkler(ca, cb)
    ka = " ".join(phonetic_key(t) for t in ca.split())
    kb = " ".join(phonetic_key(t) for t in cb.split())
    if ka and ka == kb:
        score = max(score, 0.92) if phonetic_floor else min(1.0, score + 0.02)
    return round(score, 4)


# ---------------------------------------------------------------- honorifics
HONORIFIC_SUFFIXES = {
    # canon form → gender hint (None = neutral)
    "bhai": "m", "bhaiya": "m", "bhaia": "m", "bhaisab": "m", "bhaisaheb": "m", "kaka": "m", "chacha": "m",
    "mama": "m", "dada": "m", "seth": "m", "shet": "m", "set": "m", "saheb": "m", "sahab": "m", "babu": "m",
    "uncle": "m", "ankal": "m", "bapu": "m",
    "ben": "f", "behen": "f", "bahen": "f", "behan": "f", "bai": "f", "didi": "f", "bhabhi": "f", "kaki": "f",
    "masi": "f", "mausi": "f", "chachi": "f", "aunty": "f", "anti": "f", "ammi": "f", "madam": "f", "tai": "f",
    "ji": None, "jee": None, "sir": "m",
}
HONORIFIC_PREFIXES = {"shri": "m", "shree": "m", "sri": "m", "mr": "m", "smt": "f", "shrimati": "f",
                      "mrs": "f", "ms": "f", "kumari": "f", "sushri": "f"}
_SUFFIX_CANON = {canon(k): v for k, v in HONORIFIC_SUFFIXES.items()}
_PREFIX_CANON = {canon(k): v for k, v in HONORIFIC_PREFIXES.items()}
# glued suffixes we split off ("rameshbhai" → "ramesh"), longest first
_GLUED = sorted(["bhai", "bhaiya", "ben", "behen", "bahen", "ji", "jee", "kaka", "kaki", "masi", "bhabhi",
                 "didi", "seth", "sheth"], key=len, reverse=True)


def is_honorific(token: str) -> bool:
    c = canon(token)
    return c in _SUFFIX_CANON or c in _PREFIX_CANON


def strip_honorifics(tokens: list[str]) -> tuple[list[str], str | None]:
    """Remove honorific tokens and glued honorific suffixes. Returns (name_tokens, gender_hint)."""
    gender: str | None = None
    out: list[str] = []
    for tok in tokens:
        c = canon(tok)
        if c in _PREFIX_CANON:
            gender = gender or _PREFIX_CANON[c]
            continue
        if c in _SUFFIX_CANON:
            gender = gender or _SUFFIX_CANON[c]
            continue
        low = romanize(tok).lower()
        for suf in _GLUED:
            if low.endswith(suf) and len(low) - len(suf) >= 3:
                gender = gender or HONORIFIC_SUFFIXES.get(suf)
                low = low[: -len(suf)]
                break
        out.append(low)
    return out, gender
