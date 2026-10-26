"""
Learner vocabulary: which lemmas are known, due, recently learned, lapsed or new.

Nothing personal lives in this package. The caller supplies a vocabulary-state file at
runtime, for example built from a flashcard deck:

.. code-block:: json

    {
      "words": [
        {"lemma": "ορεινός", "state": "due", "gloss": "mountainous"},
        {"lemma": "η δοκιμασία", "state": "recent"}
      ],
      "frequent": ["σπίτι", "χωριό"]
    }

``frequent`` (or a separate one-lemma-per-line file) is a list of very common lemmas
that count as known even when they are not in the learner's own list.
"""

import html
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from greek_utils.reader.text import FUNCTION_WORDS, Token, fold, function_phrase_indexes, is_greek, tokenize

# Learner states, strongest first. When a word matches several entries, the first
# state in this order wins.
STATES = ('due', 'recent', 'lesson', 'lapsed', 'known')
NEW = 'new'

# Token kinds that are not vocabulary.
FUNCTION = 'function'
NUMBER = 'number'
NAME = 'name'

ARTICLES = frozenset(fold(a) for a in ('ο', 'η', 'το', 'οι', 'τα', 'ο/η'))

# Folded inflectional endings, longest first. Stripping them gives a crude stem used
# only when no lemmatizer resolves a form (ορεινού and ορεινός share ορειν).
SUFFIXES = sorted({
    'οσ', 'ου', 'ο', 'ον', 'οι', 'ουσ', 'ων', 'ε', 'η', 'ησ', 'εσ', 'α', 'ασ', 'ι', 'ισ',
    'ια', 'ιασ', 'ιεσ', 'ιων', 'ιο', 'ιου', 'ιοι', 'ιουσ', 'ιοσ', 'ιη', 'ιησ',
    'ω', 'εισ', 'ει', 'ουμε', 'ετε', 'ουν', 'ουνε', 'ομαι', 'εσαι', 'εται', 'ομαστε',
    'εστε', 'ονται', 'ουμαι', 'ιεμαι', 'ιεται', 'ιουνται', 'ασε', 'ησε', 'ισε', 'ωσε',
    'ηκε', 'ηκαν', 'ηκα', 'σε', 'σαν', 'σα', 'ουσε', 'ουσαν',
    'μενοσ', 'μενη', 'μενο', 'μενοι', 'μενεσ', 'μενα', 'μενου', 'μενησ', 'μενων',
    'ματα', 'ματοσ', 'ματων', 'ωσ',
}, key=len, reverse=True)
MIN_STEM = 3
# A learner lemma whose stem is at least this long also matches words that start with
# it, which catches verb forms with an added aspect or voice marker (δυσκολεύ-τηκαν).
# What follows the stem must be such a marker plus an ending, so that a different word
# built on the same letters (κατοικ-ίδιο, δημοτικ-ότητα) is not taken for the lemma.
MIN_PREFIX_STEM = 6
ASPECT_MARKERS = frozenset(('', 'σ', 'ξ', 'ψ', 'κ', 'τ', 'θ'))


def stem(word: str) -> str:
    """Crude suffix-stripping stem of a folded word, never shorter than MIN_STEM."""
    key = fold(word)
    for suffix in SUFFIXES:
        if key.endswith(suffix) and len(key) - len(suffix) >= MIN_STEM:
            return key[: -len(suffix)]
    return key


def is_inflectional_continuation(rest: str) -> bool:
    """True when ``rest`` is an optional aspect marker followed by an inflectional ending."""
    return any(rest.endswith(suffix) and rest[:-len(suffix)] in ASPECT_MARKERS for suffix in SUFFIXES)


def headword(text: str) -> str:
    """
    Reduce a dictionary-style headword to its bare lemma: drop a leading article and
    trailing ending notes. ``η δοκιμασία`` → ``δοκιμασία``; ``ορεινός, -ή, -ό`` → ``ορεινός``.
    Multi-word expressions are kept whole (``μόλις και μετά βίας``).
    """
    text = re.split(r'[,(]', text, maxsplit=1)[0].strip()
    parts = text.split()
    if len(parts) > 1 and fold(parts[0]) in ARTICLES:
        parts = parts[1:]
    return ' '.join(parts)


def headword_from_card_field(field_html: str) -> str:
    """
    The Greek headword of a flashcard field that may carry examples or tables after
    the first ``<br>``: the text before the first ``<br>``, without tags or articles.
    """
    first = re.split(r'<br\s*/?>', field_html, maxsplit=1, flags=re.IGNORECASE)[0]
    first = html.unescape(re.sub(r'<[^>]+>', '', first)).strip()
    return headword(first)


class Lemmatizer(Protocol):
    """
    Anything that can propose lemmas for a surface form (kaikki index, spaCy...). It may
    also offer ``is_lexical(word) -> bool``, true when the form belongs to an ordinary
    word rather than only to proper names. Without it, nothing the lemmatizer knows is
    taken as evidence that a capitalized word is not a name.
    """

    def candidates(self, word: str) -> list[str]: ...


@dataclass(frozen=True)
class VocabEntry:
    lemma: str
    state: str
    gloss: str | None = None


@dataclass(frozen=True)
class WordInfo:
    lemma: str
    state: str  # one of STATES, NEW, FUNCTION, NUMBER or NAME
    entry: VocabEntry | None = None

    @property
    def is_vocab(self) -> bool:
        return self.state not in (FUNCTION, NUMBER, NAME)


class Vocabulary:
    """Learner word states, matched to inflected forms in running text."""

    def __init__(
        self,
        entries: Iterable[VocabEntry] = (),
        frequent: Iterable[str] = (),
        lemmatizer: Lemmatizer | None = None,
    ):
        self.entries: list[VocabEntry] = []
        self._by_key: dict[str, VocabEntry] = {}
        self._by_stem: dict[str, VocabEntry] = {}
        for entry in entries:
            if entry.state not in STATES:
                raise ValueError(f'Unknown vocabulary state {entry.state!r} for {entry.lemma!r}')
            entry = VocabEntry(headword(entry.lemma), entry.state, entry.gloss)
            self.entries.append(entry)
            self._add(self._by_key, fold(entry.lemma), entry)
            if ' ' not in entry.lemma:
                self._add(self._by_stem, stem(entry.lemma), entry)
        self._frequent_keys = {fold(headword(w)) for w in frequent}
        self._frequent_stems = {stem(headword(w)) for w in frequent if ' ' not in w.strip()}
        self.lemmatizer = lemmatizer

    def _by_prefix(self, key: str) -> VocabEntry | None:
        best = None
        for s, entry in self._by_stem.items():
            if (len(s) >= MIN_PREFIX_STEM and key.startswith(s) and (best is None or len(s) > best[0])
                    and is_inflectional_continuation(key[len(s):])):
                best = (len(s), entry)
        return best[1] if best else None

    @staticmethod
    def _add(index: dict[str, VocabEntry], key: str, entry: VocabEntry) -> None:
        current = index.get(key)
        if current is None or STATES.index(entry.state) < STATES.index(current.state):
            index[key] = entry

    @classmethod
    def from_dict(cls, data: dict, frequent: Iterable[str] = (), lemmatizer: Lemmatizer | None = None):
        entries = [
            VocabEntry(w['lemma'], w.get('state', 'known'), w.get('gloss'))
            for w in data.get('words', [])
        ]
        return cls(entries, [*data.get('frequent', []), *frequent], lemmatizer)

    @classmethod
    def from_file(cls, path: str | Path, frequent_path: str | Path | None = None,
                  lemmatizer: Lemmatizer | None = None):
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        frequent = []
        if frequent_path:
            frequent = [
                line.strip() for line in Path(frequent_path).read_text(encoding='utf-8').splitlines()
                if line.strip() and not line.startswith('#')
            ]
        return cls.from_dict(data, frequent, lemmatizer)

    def _candidates(self, word: str) -> list[str]:
        cands = [word]
        if self.lemmatizer is not None:
            cands.extend(self.lemmatizer.candidates(word))
        return cands

    def lookup(self, word: str) -> WordInfo:
        """State and lemma of one word, ignoring function words, names and numbers."""
        cands = self._candidates(word)
        for cand in cands:
            entry = self._by_key.get(fold(cand))
            if entry:
                return WordInfo(entry.lemma, entry.state, entry)
        # When the dictionary resolves the form, its lemmas decide: a learner lemma that
        # is not among them is a different word, however many letters the two share
        # (κατοικία is not κατοικώ). Stems and prefixes stand in only for a form the
        # dictionary does not know.
        if len(cands) > 1:
            lemma = cands[1]
            known = any(fold(c) in self._frequent_keys for c in cands)
            return WordInfo(lemma, 'known' if known else NEW)
        entry = self._by_stem.get(stem(word)) or self._by_prefix(fold(word))
        if entry:
            return WordInfo(entry.lemma, entry.state, entry)
        if fold(word) in self._frequent_keys or stem(word) in self._frequent_stems:
            return WordInfo(word.lower(), 'known')
        return WordInfo(word.lower(), NEW)

    def is_ordinary_word(self, word: str) -> bool:
        """
        True when the learner list, the frequent list or the lemmatizer knows the word as
        an ordinary word. A lemmatizer's proper names do not count, and a lemmatizer that
        cannot tell names from other words counts for nothing.
        """
        if self.lookup(word).state != NEW:
            return True
        is_lexical = getattr(self.lemmatizer, 'is_lexical', None)
        return is_lexical is not None and bool(is_lexical(word))

    def annotate(self, text: str) -> list[tuple[Token, WordInfo]]:
        """Every token of a text with its lemma and state."""
        tokens = tokenize(text)
        names = {t.folded for t in tokens if t.kind == 'word' and t.capitalized and not t.initial}
        in_phrase = function_phrase_indexes(text, tokens)
        out = []
        for i, t in enumerate(tokens):
            if t.kind == NUMBER:
                info = WordInfo(t.text, NUMBER)
            elif (i in in_phrase or t.folded in FUNCTION_WORDS
                  or fold(t.text.rstrip("'’ʼ")) in FUNCTION_WORDS):
                info = WordInfo(t.text.lower(), FUNCTION)
            elif t.capitalized and (not t.initial or t.folded in names) and not self._is_listed(t.text):
                info = WordInfo(t.text, NAME)
            elif not is_greek(t.text):
                info = WordInfo(t.text, NAME)  # Latin-script names and acronyms
            else:
                info = self.lookup(t.text)
            out.append((t, info))
        return out

    def _is_listed(self, word: str) -> bool:
        return self.lookup(word).state != NEW


def new_ratio(annotated: list[tuple[Token, WordInfo]]) -> tuple[float, list[str], int]:
    """Share of distinct content lemmas that are new, the new lemmas, and the lemma count."""
    is_new: dict[str, bool] = {}
    for _, info in annotated:
        if info.is_vocab:
            # Unresolved forms keep their surface as the lemma; the stem groups them
            # (κάστανα, κάστανου).
            key = stem(info.lemma)
            is_new[key] = is_new.get(key, True) and info.state == NEW
    new = sorted(k for k, n in is_new.items() if n)
    total = len(is_new)
    return (len(new) / total if total else 0.0), new, total
