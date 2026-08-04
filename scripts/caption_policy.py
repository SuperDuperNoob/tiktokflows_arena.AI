#!/usr/bin/env python3
"""
caption_policy.py - keep overlay captions off TikTok's keyword tripwires.

Two different problems, two different treatments. Mixing them up is how
accounts get struck.

1. HYPE  (price/urgency/superlative: "harga murah", "termurah", "stok last")
   Not illegal to say, but heavily keyword-filtered because every dropshipper
   spams it. reski.reski700 leans on it hard. Treatment: OBFUSCATE, the same
   way the existing preset_text.txt already does organically -
   "murrazz", "mughrahh", "disqoun", "hrga", "tigabelass". Reads native to a
   Malay TikTok audience, does not match a literal keyword filter.

2. PROHIBITED (medical//health claims: "ubat", "sembuh", "hilangkan migrain",
   "rawat anxiety")
   These are policy violations on substance, not on spelling. Obfuscating
   "ubat" to "ubaat" does NOT make the claim compliant - it is still a medical
   claim on a supplement listing, and a human reviewer or a strike report will
   read it exactly the same way. Treatment: AVOID. The AI is instructed never
   to generate them, and scan_caption() flags them so a human can rewrite.

So: obfuscation is an anti-spam-filter measure, not a compliance measure.
Never treat it as a license to make a claim you could not make in plain text.
"""
from __future__ import annotations

import hashlib
import random
import re
import unicodedata

# --------------------------------------------------------------- lexicons ----

# Hype terms. Safe to say, worth disguising. Order matters: longer phrases first
# so "paling murah" is caught before bare "murah".
HYPE_TERMS = [
    # price
    "harga salah", "salah harga", "paling murah", "termurah", "murah gila",
    "murah giler", "harga runtuh", "harga bawah", "harga kilang", "harga borong",
    "murah", "murahh", "diskaun", "diskaun besar", "diskon", "discount",
    "promo", "promosi", "sale", "offer", "free", "percuma", "jimat",
    "harga", "rebate", "cashback", "potongan",
    # urgency / scarcity
    "stok last", "last stock", "stok terhad", "stok tinggal", "tinggal sikit",
    "habis stok", "cepat grab", "grab cepat", "jangan lambat", "sekarang juga",
    "hari ini je", "hari ni je", "esok naik", "limited",
    # superlative hype
    "terbaik", "paling best", "no 1", "nombor 1", "power gila", "gila power",
    "berbaloi gila", "viral gila",
]

# Prohibited claim families. These are flagged, never silently "fixed".
PROHIBITED_PATTERNS = [
    # --- PRICE FIGURES ---
    # A number in the overlay is a promise burned into the pixels. TikTok Shop
    # prices change with vouchers, flash sales and stock, so "RM39" on a video
    # that outlives the deal is a misleading-price problem, and the video
    # cannot be corrected without a re-render. It is also the single most
    # keyword-filtered thing a dropshipper can write.
    # Obfuscation must NEVER apply here: "RM39" -> "RM3nine" is still a price.
    (r"\brm\s*\d+", "price: states a ringgit figure in the overlay"),
    (r"\d+\s*(ringgit|rgt)\b", "price: states a ringgit figure in the overlay"),
    (r"\brm\d", "price: states a ringgit figure in the overlay"),
    (r"\b(rm|myr)\s*\d", "price: states a ringgit figure in the overlay"),
    # Spelled-out prices dodge the digit patterns above.
    (r"\b(se|dua|tiga|empat|lima|enam|tujuh|lapan|sembilan)?\s*belas\s+ringgit\b",
     "price: states a price in words"),
    (r"\b(puluh|ratus)\s+ringgit\b", "price: states a price in words"),
    (r"\bubat\w*", "medical: presents product as medicine"),
    (r"\bpenawar\w*", "medical: presents product as a remedy"),
    (r"\bsembuh\w*", "medical: claims a cure"),
    (r"\brawat\w*", "medical: claims treatment"),
    (r"\bmerawat\b", "medical: claims treatment"),
    (r"\bhilangkan\s+(sakit|migrain|anxiety|penyakit|demam|batuk|kanser)\w*",
     "medical: claims to eliminate a condition"),
    (r"\bhilang\s+(migrain|anxiety|penyakit|kanser)\w*",
     "medical: claims to eliminate a condition"),
    (r"\b(migrain|anxiety|depression|kanser|cancer|diabetes|darah tinggi|asma)\b",
     "medical: names a medical condition"),
    (r"\bcure[sd]?\b", "medical: claims a cure"),
    (r"\btreat(s|ment)?\b", "medical: claims treatment"),
    (r"\bheal(s|ing)?\b", "medical: claims healing"),
    (r"\bfda\b|\bkkm\b|\bapproved\b|\bdiluluskan\b", "regulatory: implies official approval"),
    (r"\b100\s*%\s*(berkesan|effective|guarantee\w*|jamin\w*)",
     "absolute: unqualified efficacy guarantee"),
    (r"\bguarantee\w*\b|\bdijamin\b|\bjaminan\b", "absolute: guarantee claim"),
    (r"\bkurus\w*\s+(dalam|in)\s+\d+", "medical: time-bound weight loss claim"),
    (r"\bslimming\b|\bpelangsing\b", "medical: weight-loss claim"),
    (r"\bwhatsapp\b|\bwasap\b|\bdm\s+saya\b|\btelegram\b|\bwa\s*:\s*\d",
     "off-platform: directs traffic away from TikTok"),
    (r"\bcod\s+sahaja\b|\bcod\s+only\b", "off-platform: off-app transaction"),
    # --- OVERCLAIM ---
    # Absolute/unverifiable superlatives. Unlike hype ("murah"), these assert a
    # fact that can be checked and disproved, so disguising the spelling does
    # not help - the claim is the problem.
    (r"\bterbaik\s+di\s+(dunia|malaysia|market|pasaran)\b",
     "overclaim: unverifiable superlative"),
    (r"\b(no|nombor)\.?\s*1\s+di\s+(dunia|malaysia|pasaran)\b",
     "overclaim: unverifiable ranking"),
    (r"\b100\s*%\s*(asli|original|selamat|berkesan)\b",
     "overclaim: absolute quality guarantee"),
    (r"\bpaling\s+(berkesan|power|hebat)\b", "overclaim: unverifiable superlative"),
    (r"\bmesti\s+(kurus|cantik|putih|sembuh)\b", "overclaim: guaranteed outcome"),
    # "hilang" deliberately excluded: in these captions it means stock selling
    # out ("confirm hilang"), not a body/health outcome.
    (r"\bconfirm\s+(kurus|putih|sembuh|jerawat\s+hilang)\b",
     "overclaim: guaranteed outcome"),
    (r"\bterus\s+(kurus|putih|sembuh)\b", "overclaim: guaranteed instant result"),
    (r"\bdalam\s+\d+\s*(hari|minggu)\s+(kurus|putih|sembuh|hilang)",
     "overclaim: time-bound guaranteed result"),
    (r"\btanpa\s+(kesan\s+sampingan|side\s*effect)", "overclaim: safety guarantee"),
]

# Medical wording -> compliant lifestyle wording. Applied by soften_claims()
# so a caption is repaired rather than thrown away. These deliberately drop
# the claim ("cures X") and keep only the vibe ("feels fresh"), because a
# supplement/cosmetic listing may describe an experience but not an effect.
MEDICAL_SUBSTITUTIONS: list[tuple[str, str]] = [
    (r"\bubat\s+(kurus|pelangsing|slimming)\w*", "teman diet"),
    (r"\bubat\s+(jerawat|kulit)\w*", "penjagaan kulit"),
    (r"\bubat\w*", "pilihan harian"),
    (r"\bpenawar\w*", "pilihan harian"),
    (r"\bsembuh\w*", "rasa lega"),
    (r"\bmerawat\b", "menjaga"),
    (r"\brawat\w*", "menjaga"),
    (r"\bhilangkan\s+(sakit|migrain|penyakit|demam|batuk)\w*", "bantu rasa selesa"),
    (r"\bhilang\s+(migrain|anxiety|penyakit)\w*", "rasa lebih tenang"),
    (r"\b(migrain|anxiety|depression|kanser|cancer|diabetes|darah tinggi|asma)\b",
     "hari yang penat"),
    (r"\b(slimming|pelangsing)\b", "teman diet"),
    (r"\bkurus\s+dalam\s+\d+\s*\w*", "kekal aktif"),
    (r"\bdetox\w*", "rutin harian"),
    (r"\bcure[sd]?\b", "supports"),
    (r"\btreat(s|ment)?\b", "care"),
    (r"\bheal(s|ing)?\b", "comfort"),
]

# Substitutions that read as native Malay TikTok slang. Mirrors the style
# already present in preset_text.txt.
_PHONETIC = {
    "murah":   ["mughrahh", "murrahh", "muraahh", "mughrah", "murrazz"],
    "harga":   ["hrga", "ha-rga", "hargaa", "hrgaa", "harghaa"],
    "diskaun": ["disqoun", "diskaunn", "dizkaun", "disqaun"],
    "diskon":  ["disqon", "dizkon"],
    "discount":["disqount", "diskount"],
    "promo":   ["promoo", "prom0", "promoh"],
    "promosi": ["promosii", "promoosi"],
    "free":    ["freee", "fr33", "phree"],
    "percuma": ["percumaa", "percumah", "pecuma"],
    "sale":    ["salee", "sal3", "saleee"],
    "stok":    ["stokk", "st0k", "stokh"],
    "terbaik": ["terbaikk", "terbaiqq", "terbaeq"],
    "viral":   ["virall", "vir4l", "viraal"],
    "gila":    ["gilaa", "gilerr", "gilazz"],
    "limited": ["limitedd", "limit3d"],
    "jimat":   ["jimatt", "jimaat"],
    "offer":   ["offerr", "0ffer"],
}

# Reverse of _PHONETIC for dedup: disguised spelling -> base word. Keys are
# run-collapsed the same way dedup_key() collapses its input, so "muraahh"
# and "murrahh" both arrive as "murah" and match.
def _collapse(w: str) -> str:
    return re.sub(r"(.)\1+", r"\1", re.sub(r"[^a-z]+", "", w.lower()))


# Words are compared on their first N letters in dedup_key(). 4 keeps short
# Malay function words (yang, tapi, kena) distinct while tolerating the
# suffix/vowel damage obfuscation does to longer words.
_KEY_PREFIX = 4

_PHONETIC_BASE: dict[str, str] = {}
for _base, _variants in _PHONETIC.items():
    for _v in _variants:
        _PHONETIC_BASE[_collapse(_v)] = _collapse(_base)
    _PHONETIC_BASE[_collapse(_base)] = _collapse(_base)

_VOWELS = "aeiou"


def _rng(text: str, seed: int | None) -> random.Random:
    """Deterministic per-word RNG so the same word+seed always maps the same."""
    h = hashlib.md5(f"{seed}:{text}".encode("utf-8")).hexdigest()
    return random.Random(int(h[:8], 16))


# ---------------------------------------------------------- transformations ----

def _t_double_last_consonant(w: str, r: random.Random) -> str:
    for i in range(len(w) - 1, -1, -1):
        if w[i].isalpha() and w[i].lower() not in _VOWELS:
            return w[:i + 1] + w[i] + w[i + 1:]
    return w + w[-1]


def _t_trailing_double(w: str, r: random.Random) -> str:
    return w + r.choice([w[-1], w[-1] * 2, "h", "z" * 2, "s"])


def _t_drop_vowel(w: str, r: random.Random) -> str:
    idx = [i for i in range(1, len(w) - 1) if w[i].lower() in _VOWELS]
    if not idx:
        return w
    i = r.choice(idx)
    return w[:i] + w[i + 1:]


def _t_hyphen(w: str, r: random.Random) -> str:
    if len(w) < 4:
        return w
    i = r.randint(2, len(w) - 2)
    return w[:i] + "-" + w[i:]


def _t_repeat_vowel(w: str, r: random.Random) -> str:
    idx = [i for i in range(len(w)) if w[i].lower() in _VOWELS]
    if not idx:
        return w
    i = r.choice(idx)
    return w[:i + 1] + w[i] + w[i + 1:]


def _t_gh(w: str, r: random.Random) -> str:
    idx = [i for i in range(1, len(w)) if w[i].lower() in _VOWELS]
    if not idx:
        return w
    i = r.choice(idx)
    return w[:i] + "gh" + w[i:]


_TRANSFORMS = [
    _t_double_last_consonant,
    _t_trailing_double,
    _t_drop_vowel,
    _t_hyphen,
    _t_repeat_vowel,
    _t_gh,
]


def obfuscate_word(word: str, seed: int | None = None) -> str:
    """Disguise one hype word while keeping it phonetically readable."""
    if len(word) < 3:
        return word
    r = _rng(word, seed)
    low = word.lower()

    # Prefer a curated spelling; they read the most natural.
    if low in _PHONETIC and r.random() < 0.75:
        out = r.choice(_PHONETIC[low])
    else:
        out = _TRANSFORMS[r.randrange(len(_TRANSFORMS))](word, r)
        # Occasionally stack a second, light transform.
        if r.random() < 0.3:
            out = _t_trailing_double(out, r)

    # Preserve capitalisation of the original.
    if word[0].isupper():
        out = out[0].upper() + out[1:]
    return out


def obfuscate_phrase(phrase: str, seed: int | None = None) -> str:
    return " ".join(obfuscate_word(w, seed) for w in phrase.split())


# ------------------------------------------------------------------- API ----

_HYPE_RE = re.compile(
    r"(?<!\w)(" + "|".join(re.escape(t) for t in
                           sorted(HYPE_TERMS, key=len, reverse=True)) + r")(?!\w)",
    re.IGNORECASE)


def find_hype(text: str) -> list[str]:
    return [m.group(0) for m in _HYPE_RE.finditer(text or "")]


def find_prohibited(text: str) -> list[tuple[str, str]]:
    """[(matched_text, why)] for claims that must be rewritten, not disguised."""
    if not text:
        return []
    low = unicodedata.normalize("NFKC", text).lower()
    out = []
    for pat, why in PROHIBITED_PATTERNS:
        for m in re.finditer(pat, low, re.IGNORECASE):
            out.append((m.group(0).strip(), why))
    # Dedup, keep order.
    seen, res = set(), []
    for t, w in out:
        if (t, w) not in seen:
            seen.add((t, w))
            res.append((t, w))
    return res


def soften(text: str, seed: int | None = None, rate: float = 1.0) -> str:
    """Obfuscate hype terms in `text`.

    rate < 1.0 leaves some occurrences untouched, which looks more organic than
    disguising every single one.
    """
    if not text:
        return text
    r = random.Random(seed if seed is not None else random.randrange(1 << 30))

    def repl(m: re.Match) -> str:
        if r.random() > rate:
            return m.group(0)
        return obfuscate_phrase(m.group(0), seed)

    return _HYPE_RE.sub(repl, text)


def dedup_key(text: str) -> str:
    """Identity of a caption ignoring obfuscation, emoji and punctuation.

    soften() is deliberately random, so the same source caption comes out as
    "murah", "muraahh" or "mughrahh" on different runs. A plain lowercase
    comparison therefore treats all of them as new captions and the pool fills
    with the same line spelled five ways. Normalising undoes the specific
    things obfuscation does:
      - strip everything that is not a letter or space (emoji, hyphens, digits
        from leetspeak like fr33)
      - collapse runs of a repeated letter, so muraahh -> murah
      - map the curated phonetic spellings back to their base word
    Cheap and lossy on purpose: it only needs to answer "have we already got
    this line", not reconstruct the original.
    """
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", text).lower()
    s = re.sub(r"[^a-z\s]+", "", s)          # emoji, punctuation, leet digits
    s = re.sub(r"(.)\1+", r"\1", s)          # muraahh -> murah, gilaa -> gila
    words = []
    for w in s.split():
        w = _PHONETIC_BASE.get(w, w)
        # Transforms also insert "gh", drop an interior vowel and append a
        # junk consonant, none of which run-collapsing undoes
        # (tinggal -> tinggaals -> "tingals"). Comparing a short prefix of
        # each word absorbs all of those: a false merge would need every
        # word in both captions to agree on its first few letters.
        w = w.replace("gh", "g")
        w = w[:_KEY_PREFIX]
        words.append(w)
    return " ".join(words)


# Overlay text is burned into pixels at ~62-82px on a 1080-wide frame, so it
# has to fit 1-2 short lines or it wraps into a wall and covers the product.
MAX_CAPTION_CHARS = 70
MAX_CAPTION_LINES = 2
MAX_LINE_CHARS = 38


def soften_claims(text: str) -> tuple[str, list[str]]:
    """Rewrite medical wording into compliant lifestyle wording.

    Returns (new_text, notes). Prices and overclaims are NOT repaired here:
    a price has no compliant equivalent and an overclaim only becomes safe by
    deleting the assertion, so both are dropped by the caller instead.
    """
    if not text:
        return text, []
    out, notes = text, []
    for pat, repl in MEDICAL_SUBSTITUTIONS:
        new = re.sub(pat, repl, out, flags=re.IGNORECASE)
        if new != out:
            notes.append(f"{pat} -> {repl}")
            out = new
    return re.sub(r"\s{2,}", " ", out).strip(), notes


_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF\u2B00-\u2BFF]+")
# Clause boundaries a Malay caption naturally breaks on.
_CLAUSE_RE = re.compile(r"[,.!?;:]|\s(?=(?:tapi|sebab|dahla|ni kalau|kalau)\b)")


def shorten(text: str, max_chars: int = MAX_CAPTION_CHARS,
            max_lines: int = MAX_CAPTION_LINES) -> str:
    """Clamp a caption to 1-2 short lines without leaving it mid-thought.

    A hard character cut produces things like "aku baru nak berjimatt" with the
    payoff missing, which reads as broken on screen. So: prefer the largest
    whole clause that fits, fall back to a word boundary, and re-attach a
    trailing emoji since that carries the tone.
    """
    if not text:
        return text
    words = " ".join(text.split())
    if len(words) > max_chars:
        tail = _EMOJI_RE.findall(words)
        emoji = tail[-1][:2] if tail else ""
        budget = max_chars - (len(emoji) + 1 if emoji else 0)

        # Largest clause boundary that fits.
        cut_at = -1
        for m in _CLAUSE_RE.finditer(words):
            if m.end() <= budget:
                cut_at = m.end()
            else:
                break
        if cut_at < budget * 0.45:          # no useful clause: use a word break
            cut = words[:budget]
            sp = cut.rfind(" ")
            cut_at = sp if sp > budget * 0.5 else budget
        words = words[:cut_at].rstrip(" ,.-;:")
        # If the cut still left a dangling connector, drop that last word -
        # "sebelum hrgq back" reads worse than stopping a word earlier.
        _DANGLING = {"dan", "atau", "tapi", "sebab", "yang", "nak", "dah", "je",
                     "ni", "tu", "la", "weh", "kot", "macam", "sampai", "terus",
                     "lagi", "dia", "aku", "korang", "kalau", "kalu", "sebelum",
                     "back", "to", "buat", "jadi", "bagi", "masih", "still"}
        parts = words.split()
        while len(parts) > 3 and parts[-1].lower().strip(",.!?") in _DANGLING:
            parts.pop()
        words = " ".join(parts).rstrip(" ,.-;:")
        if emoji and not words.endswith(emoji):
            words = f"{words} {emoji}"
    if max_lines <= 1 or len(words) <= MAX_LINE_CHARS:
        return words
    # Two lines: split near the middle on a word boundary so neither line runs
    # past the frame.
    mid = len(words) // 2
    left = words.rfind(" ", 0, mid + 1)
    right = words.find(" ", mid)
    idx = max((i for i in (left, right) if i > 0),
              key=lambda i: -abs(i - mid), default=-1)
    return f"{words[:idx]}\n{words[idx + 1:]}" if idx > 0 else words


def is_too_long(text: str) -> bool:
    t = (text or "").strip()
    return len(t) > MAX_CAPTION_CHARS or (t.count("\n") + 1) > MAX_CAPTION_LINES


def scan_caption(text: str) -> dict:
    """Full report for one caption."""
    prohibited = find_prohibited(text)
    hype = find_hype(text)
    return {
        "text": text,
        "hype_terms": hype,
        "prohibited": prohibited,
        "needs_obfuscation": bool(hype),
        "needs_rewrite": bool(prohibited),
        "risk": "high" if prohibited else ("medium" if hype else "low"),
    }


# The block appended to every AI prompt that produces captions.
AI_CAPTION_RULES = """
PERATURAN POLISI TIKTOK (WAJIB IKUT):

A. JANGAN SESEKALI tulis (ini melanggar polisi, bukan boleh diselamatkan
   dengan tukar ejaan - jangan tulis langsung):
   - HARGA DALAM NOMBOR: RM39, RM 39, MYR55, "39 ringgit", "tigabelas
     ringgit". DILARANG SAMA SEKALI. Harga TikTok Shop berubah ikut voucher
     dan flash sale, tapi teks overlay dibakar kekal dalam video - harga
     lama jadi menipu dan video tak boleh dibetulkan tanpa render semula.
     Cakap "mughrahh" atau "hrga jatuh" sahaja, JANGAN sebut nombor.
   - Dakwaan perubatan: ubat, penawar, sembuh, rawat, hilangkan migrain,
     hilangkan anxiety, kanser, diabetes, darah tinggi, slimming, pelangsing
   - Dakwaan melampau: terbaik di dunia/Malaysia, no 1 di Malaysia,
     100% asli, 100% berkesan, mesti kurus, confirm putih, tanpa kesan
     sampingan, kurus dalam 7 hari
   - Jaminan mutlak: 100% berkesan, dijamin, guaranteed
   - Kelulusan pihak berkuasa: KKM, FDA, diluluskan
   - Arahan keluar platform: WhatsApp, DM, Telegram, COD sahaja
   Untuk produk kesihatan/supplement, cakap pengalaman peribadi dan rasa
   sahaja ("lepas minum rasa segar"), JANGAN cakap ia merawat penyakit.

B. Untuk perkataan hype harga/urgency (murah, harga, diskaun, promo, free,
   stok last, terbaik), tulis dengan ejaan slanga TikTok yang senget supaya
   tak kena filter kata kunci automatik. Gaya rojak Malaysia yang natural:
     murah    -> mughrahh / murrazz / muraahh
     harga    -> hrga / ha-rga / harghaa
     diskaun  -> disqoun / dizkaun
     free     -> freee / phree
     stok     -> stokk / st0k
     terbaik  -> terbaiqq
   Jangan buat semua perkataan senget - 1 hingga 2 sahaja setiap caption,
   supaya masih senang dibaca dan nampak organik.

C. Caption mesti masih mudah difahami orang Malaysia. Kalau dah tak boleh
   baca, ia gagal.

D. PANJANG: maksimum 70 aksara, 1 hingga 2 baris pendek sahaja. Teks ini
   dibakar atas video pada saiz besar - kalau panjang ia akan wrap jadi
   satu blok dan tutup produk. Pendek dan padu lebih baik.
"""


def _demo() -> None:
    samples = [
        "harga murah gila hari ni, stok last 🔥",
        "ubat penawar migrain, hilangkan anxiety terus",
        "diskaun 40% je hari ni, cepat grab sebelum habis",
        "tiba tiba jadi belas ringgit je 😭 beg kuning bawah",
        "100% dijamin berkesan, whatsapp saya untuk order",
    ]
    for s in samples:
        rep = scan_caption(s)
        print(f"\n  IN   : {s}")
        print(f"  risk : {rep['risk']}")
        if rep["prohibited"]:
            for t, w in rep["prohibited"]:
                print(f"  BLOCK: {t!r} -> {w}")
        print(f"  OUT  : {soften(s, seed=7)}")


if __name__ == "__main__":
    _demo()
