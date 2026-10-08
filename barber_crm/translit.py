"""O'zbek lotin -> kirill (avtomatik). HTML teglar, /buyruqlar va CRM so'zi o'zgarmaydi."""
import re

_APOS = "‘’ʻʼ`´'"
_VOWELS = "aeiouAEIOU"
_PROTECT = re.compile(r"(<[^>]+>|&\w+;|(?<!\S)/[A-Za-z_]+|https?://\S+|@\w+|\bCRM\b)")
_SINGLE = {
    "a": "а", "b": "б", "c": "ц", "d": "д", "e": "е", "f": "ф", "g": "г", "h": "ҳ", "i": "и",
    "j": "ж", "k": "к", "l": "л", "m": "м", "n": "н", "o": "о", "p": "п", "q": "қ", "r": "р",
    "s": "с", "t": "т", "u": "у", "v": "в", "w": "в", "x": "х", "y": "й", "z": "з",
}
_DOUBLE = {"sh": "ш", "ch": "ч", "yo": "ё", "yu": "ю", "ya": "я", "ye": "е"}


def _case(src, out):
    if len(src) > 1 and src.isupper():
        return out.upper()
    if src[0].isupper():
        return out[0].upper() + out[1:]
    return out


def _convert(text):
    res = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        low = ch.lower()
        nxt = text[i + 1] if i + 1 < n else ""
        # o‘ / g‘
        if low in "og" and nxt and nxt in _APOS:
            res.append(_case(ch + nxt, "ў" if low == "o" else "ғ")); i += 2; continue
        # tutuq belgisi: a'lo -> аъло
        if ch in _APOS and i > 0 and text[i - 1] in _VOWELS:
            res.append("ъ"); i += 1; continue
        pair = (ch + nxt).lower()
        after = text[i + 2] if i + 2 < n else ""
        if pair in _DOUBLE and not (pair == "yo" and after in _APOS and after):
            res.append(_case(ch + nxt, _DOUBLE[pair])); i += 2; continue
        if low in _SINGLE:
            prev = text[i - 1] if i > 0 else ""
            out = "э" if (low == "e" and not prev.isalpha()) else _SINGLE[low]
            res.append(_case(ch, out)); i += 1; continue
        res.append(ch); i += 1
    return "".join(res)


def to_cyrillic(text):
    if not text:
        return text
    parts = _PROTECT.split(text)
    # split() bilan toq indekslar - himoyalangan bo'laklar
    return "".join(p if k % 2 else _convert(p) for k, p in enumerate(parts))
