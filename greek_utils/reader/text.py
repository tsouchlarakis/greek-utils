"""
Greek text normalization, tokenization and sentence splitting.

Two comparison keys are used throughout the reader:

- ``fold``: lower case, every diacritic removed, final sigma made medial. Two words
  with the same fold are "the same letters" (πότε, ποτέ and ΠΟΤΕ all fold to ποτε).
- ``strict``: lower case and final sigma made medial, accents kept. Two words with the
  same strict key are the same written word.
"""

import re
import unicodedata
from dataclasses import dataclass

APOSTROPHES = "'’ʼ`"

# A letter is a letter or a combining mark, so a decomposed accent (α + U+0301) stays
# inside its word. A word is letters, optionally joined by internal apostrophes
# (σ'αυτό), optionally ending in an elision apostrophe (απ'). A number is digits with
# . or , separators, optionally followed by letters (35χρονος).
_LETTER = r"(?:[^\W\d_]|[\u0300-\u036f])"
TOKEN_RE = re.compile(
    rf"(?P<number>\d+(?:[.,]\d+)*{_LETTER}*)"
    rf"|(?P<word>{_LETTER}+(?:[{APOSTROPHES}]{_LETTER}+)*[{APOSTROPHES}]?)"
)

# A sentence runs up to terminal punctuation (. ! ; Greek question mark ; ellipsis),
# optionally followed by a closing quote, then whitespace or the end of the text.
SENTENCE_RE = re.compile(r".+?(?:[.!;;…]+[»”\"']?(?=\s|$)|$)", re.DOTALL)

ACUTE = '́'


def strict(word: str) -> str:
    """Lower case with final sigma made medial; accents kept."""
    s = unicodedata.normalize('NFD', word.lower())
    # Keep only the acute accent, so that dialytika and breathing marks never decide
    # whether two words differ.
    s = ''.join(c for c in s if not unicodedata.combining(c) or c == ACUTE)
    s = s.replace('ς', 'σ')
    for a in APOSTROPHES:
        s = s.replace(a, "'")
    return unicodedata.normalize('NFC', s)


def fold(word: str) -> str:
    """Lower case, no diacritics, final sigma made medial, apostrophes dropped."""
    s = unicodedata.normalize('NFD', word.lower())
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.replace('ς', 'σ')
    for a in APOSTROPHES:
        s = s.replace(a, '')
    return s


def accent_positions(words: list[str]) -> set[int]:
    """
    Indexes, in the letters of the words laid end to end, of the letters carrying an
    acute accent (tonos). Apostrophes are not letters, so an elided σ' and the σ of
    σαυτό count the same.
    """
    found = set()
    letters = 0
    for word in words:
        for c in unicodedata.normalize('NFD', word.lower()):
            if c == ACUTE:
                found.add(letters - 1)
            elif not unicodedata.combining(c) and c not in APOSTROPHES:
                letters += 1
    return found


def accent_position(word: str) -> int | None:
    """Index of the letter carrying the acute accent (tonos), or None if unaccented."""
    found = accent_positions([word])
    return min(found) if found else None


# Number words, recognized on folded forms as a stem plus an inflectional ending, so
# that inflected cardinals (χιλίων, διακοσίους, τριών) and ordinals (εικοσιπέμπτη,
# τριακοστή) are numbers as much as their dictionary forms.
_UNITS = 'ενα|ενασ|μια|μια|δυο|τρια|τρεισ|τεσσερα|τεσσερισ|πεντε|εξι|επτα|εφτα|οκτω|οχτω|εννεα|εννια'
_TENS = 'εικοσι|τριαντα|σαραντα|πενηντα|εξηντα|εβδομηντα|ογδοντα|ενενηντα'
_ORDINAL_UNITS = 'πρωτ|δευτερ|τριτ|τεταρτ|πεμπτ|εκτ|εβδομ|ογδο|εν{1,2}ατ'
_ORDINAL_STEMS = (
    rf'{_ORDINAL_UNITS}|δεκατ|ενδεκατ|εντεκατ|δωδεκατ'
    r'|εικοστ|τριακοστ|τεσσαρακοστ|πεντηκοστ|εξηκοστ|εβδομηκοστ|ογδοηκοστ|ενενηκοστ'
    r'|εκατοστ|(?:δια|τρια|τετρα|πεντα|εξα|επτα|εφτα|οκτα|οχτα|εννια|εννεα)κοσιοστ|χιλιοστ'
)
_ADJ_ENDING = 'οσ|ου|ο|ον|οι|ουσ|ων|ε|η|ησ|εσ|α'
_NUMBER_WORD_RE = re.compile(
    r'^(?:'
    rf'μηδεν|{_UNITS}|τριων|τεσσαρων|δεκα|εντεκα|δωδεκα|δεκα(?:{_UNITS})'
    rf'|{_TENS}|(?:{_TENS})(?:{_UNITS})|εκατο|εκατον'
    rf'|(?:δια|τρια|τετρα|πεντα|εξα|επτα|εφτα|οκτα|οχτα|εννια|εννεα)κοσι(?:{_ADJ_ENDING})'
    rf'|χιλι(?:{_ADJ_ENDING}|αδα|αδεσ|αδων)|(?:δισ)?εκατομμυρι(?:ο|α|ου|ων)'
    r'|δεκαδ(?:α|εσ|ων)|εκατονταδ(?:α|εσ|ων)'
    rf'|(?:(?:{_TENS})(?:{_ORDINAL_UNITS})|{_ORDINAL_STEMS})(?:{_ADJ_ENDING})'
    r'|κομμα'
    r')$'
)

# Number words that are mostly something else, told apart only by context: ένα, μια,
# ένας are the indefinite article far more often than the numeral, and κόμμα is a
# comma in "τρία κόμμα πέντε" but mostly a political party. Never checked.
AMBIGUOUS_NUMBER_WORDS = frozenset(fold(w) for w in 'ένα ένας μία μια κόμμα'.split())
# Written words that fold like a number word but are not one; told apart by the accent
# (εκτός "except" against έκτος "sixth").
NOT_NUMBER_WORDS = frozenset(strict(w) for w in 'εκτός'.split())
# Ordinals that are as often "first", "second", "earlier", "secondary" as a rank in a
# sequence. Telling the senses apart needs a parser, so a mismatch is reported as an
# advisory warning rather than a failure.
_ADVISORY_ORDINAL_RE = re.compile(rf'^(?:πρωτ|δευτερ)(?:{_ADJ_ENDING})$')


def is_number_word(word: str) -> bool:
    key = fold(word)
    if key.isdigit():
        return True
    return bool(_NUMBER_WORD_RE.match(key)) and strict(word) not in NOT_NUMBER_WORDS


def is_spelled_quantity(word: str) -> bool:
    """A number spelled out in words, excluding words that are mostly something else."""
    return is_number_word(word) and not word.isdigit() and fold(word) not in AMBIGUOUS_NUMBER_WORDS


def is_advisory_quantity(word: str) -> bool:
    """A spelled-out ordinal whose numeric sense cannot be told from context (πρώτη φορά)."""
    return bool(_ADVISORY_ORDINAL_RE.match(fold(word)))


def is_greek(word: str) -> bool:
    return any('GREEK' in unicodedata.name(c, '') for c in word if c.isalpha())


@dataclass(frozen=True)
class Token:
    text: str
    start: int
    end: int
    kind: str  # 'word' or 'number'
    sentence: int  # index of the sentence the token belongs to
    initial: bool  # first word of a sentence or of a quotation

    @property
    def folded(self) -> str:
        return fold(self.text)

    @property
    def capitalized(self) -> bool:
        return self.text[:1].isupper()


def sentences(text: str) -> list[str]:
    """Split text into sentences, keeping their punctuation."""
    return [m.group(0).strip() for m in SENTENCE_RE.finditer(text) if m.group(0).strip()]


def tokenize(text: str) -> list[Token]:
    """Tokenize text into words and numbers, with sentence membership."""
    tokens = []
    for s_idx, m_sent in enumerate(m for m in SENTENCE_RE.finditer(text) if m.group(0).strip()):
        offset = m_sent.start()
        sentence_text = m_sent.group(0)
        first = True
        prev_end = 0
        for m in TOKEN_RE.finditer(sentence_text):
            gap = sentence_text[prev_end:m.start()]
            # A quotation or a colon starts a new clause whose first word is capitalized.
            initial = first or any(c in gap for c in '«“":')
            kind = 'number' if m.group('number') else 'word'
            tokens.append(Token(
                text=m.group(0),
                start=offset + m.start(),
                end=offset + m.end(),
                kind=kind,
                sentence=s_idx,
                initial=initial,
            ))
            first = False
            prev_end = m.end()
    return tokens


def words(text: str) -> list[str]:
    """The word and number tokens of a text, as strings."""
    return [t.text for t in tokenize(text)]


def levenshtein(a: str, b: str) -> int:
    """Character edit distance."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


# Closed-class words, folded. They are never targets and never count toward the
# new-word ratio.
FUNCTION_WORDS = frozenset(fold(w) for w in '''
    ο η το οι τα του της των τον την τη τους τις
    ένας ένα μια μία ενός μιας έναν
    στο στη στην στον στα στου στης στων στους στις σε σ' με για από προς χωρίς ως
    μέχρι ώς παρά κατά μετά πριν πάνω κάτω μέσα έξω δίπλα
    και κι ή ούτε ουδέ αλλά όμως ενώ αν εάν να θα δεν δε μην μη ας ότι πως πώς
    που πού όταν καθώς επειδή γιατί αφού ώστε ενώ όπως όπου
    εγώ εσύ αυτός αυτή αυτό αυτοί αυτές αυτά εμείς εσείς
    μου σου μας σας τους τού τής μού σού
    είμαι είσαι είναι είμαστε είστε ήμουν ήταν ήταν
    αυτού αυτής αυτών αυτόν αυτήν
    ποιος ποια ποιο τι τίποτα κάτι κάθε
    οποίος οποία οποίο οποίου οποίας οποίων οποίους οποίες
    πολύ πιο ήδη ακόμα ακόμη επίσης μόνο έτσι εδώ εκεί τώρα όχι ναι
'''.split())
