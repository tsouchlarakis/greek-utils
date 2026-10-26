"""
Glosses for tap-a-word, resolved without inventing translations.

Order: the learner's own vocabulary file (its ``gloss``), then Wiktionary through a
kaikki.org Greek extract (JSON lines, one entry per line, downloaded separately), then
Glosbe. A contextual explainer (for example a model call for multi-word expressions)
can be plugged in last; its glosses are labeled so they are never mistaken for
dictionary entries.
"""

import json
import re
import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

from greek_utils.reader.text import fold
from greek_utils.reader.vocab import Vocabulary

SOURCE_DECK = 'deck'
SOURCE_WIKTIONARY = 'wiktionary'
SOURCE_GLOSBE = 'glosbe'
SOURCE_CONTEXT = 'context'

# kaikki form tags that are not inflected forms of the word.
SKIP_FORM_TAGS = {'romanization', 'table-tags', 'inflection-template', 'class', 'canonical'}

# Senses a reader of current text rarely needs; they go after the others.
RARE_SENSE_TAGS = frozenset({'archaic', 'obsolete', 'rare', 'dated', 'historical', 'dialectal'})


@dataclass(frozen=True)
class SenseCue:
    """
    Context words (folded word beginnings) that make senses with these English words,
    or these kaikki topics, the likely ones. Wiktionary lists senses in historical or
    literal order, so its first sense is often not the one a news text means.
    """
    context: re.Pattern
    sense: re.Pattern
    topics: frozenset[str] = frozenset()


SENSE_CUES = (
    # Social media and reported speech: ανάρτηση is a post, not a hanging.
    SenseCue(
        context=re.compile(
            r'\b(?:facebook|instagram|twitter|tiktok|youtube|linkedin|telegram|threads|x\b'
            r'|μεσα κοινωνικησ δικτυωσησ|social media|διαδικτ|ιστοσελιδ|ιστολογ|λογαριασμ'
            r'|δημοσιευ|σχολιασ|ανεφερ|αναφερ|εγραψ|γραφει|σημειωσ|σημειων|δηλωσ|δηλων|τονισ)'
        ),
        sense=re.compile(r'\b(?:post|posting|tweet|online|internet|blog|message|statement|announcement)\b'),
        topics=frozenset({'internet', 'computing', 'social-media'}),
    ),
)


@dataclass(frozen=True)
class Gloss:
    lemma: str
    text: str
    source: str
    pos: str | None = None
    etymology: str | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(frozen=True)
class Sense:
    gloss: str
    tags: frozenset[str] = frozenset()
    topics: frozenset[str] = frozenset()


@dataclass(frozen=True)
class DictEntry:
    word: str
    pos: str | None
    glosses: tuple[str, ...]
    etymology: str | None
    senses: tuple[Sense, ...] = ()


def rank_senses(entries: list[DictEntry], context: str = '') -> list[str]:
    """
    The glosses of the entries, most likely first: a sense the context points to (see
    SENSE_CUES), then the rest in Wiktionary's order, rare and archaic senses last.
    """
    key = fold(context)
    cues = [cue for cue in SENSE_CUES if key and cue.context.search(key)]
    ranked = []
    for entry in entries:
        senses = entry.senses or tuple(Sense(g) for g in entry.glosses)
        for sense in senses:
            topics = {t.lower() for t in sense.topics}
            cued = any(cue.sense.search(sense.gloss.lower()) or cue.topics & topics for cue in cues)
            rare = bool(RARE_SENSE_TAGS & sense.tags)
            ranked.append((not cued, rare, len(ranked), sense.gloss))
    return [gloss for *_, gloss in sorted(ranked)]


class KaikkiDictionary:
    """
    An in-memory index of a kaikki.org Wiktionary extract: headwords with their senses,
    and every inflected form mapped back to its headwords. It doubles as a lemmatizer.
    """

    def __init__(self, records: Iterable[dict]):
        self._entries: dict[str, list[DictEntry]] = defaultdict(list)
        self._forms: dict[str, list[str]] = defaultdict(list)
        self._lexical: set[str] = set()  # folded forms of words that are not proper names
        for rec in records:
            if rec.get('lang_code', 'el') != 'el' or not rec.get('word'):
                continue
            self._add(rec)

    @classmethod
    def load(cls, path: str | Path) -> 'KaikkiDictionary':
        def records():
            with open(path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        yield json.loads(line)
        return cls(records())

    def _add_form(self, form: str, lemma: str, lexical: bool) -> None:
        key = fold(form)
        if lemma not in self._forms[key]:
            self._forms[key].append(lemma)
        if lexical:
            self._lexical.add(key)

    def _add(self, rec: dict) -> None:
        word = rec['word']
        # Proper names are tagged pos "name"; a capitalized headword is one too.
        lexical = rec.get('pos') != 'name' and not word[:1].isupper()
        glosses = []
        senses = []
        for sense in rec.get('senses', []):
            form_of = sense.get('form_of') or sense.get('alt_of')
            if form_of:
                for target in form_of:
                    if target.get('word'):
                        self._add_form(word, target['word'], lexical)
                continue
            if sense.get('glosses'):
                glosses.append(sense['glosses'][-1])
                senses.append(Sense(
                    sense['glosses'][-1],
                    frozenset(sense.get('tags', [])),
                    frozenset(sense.get('topics', [])),
                ))
        if glosses:
            self._entries[fold(word)].append(DictEntry(
                word=word,
                pos=rec.get('pos'),
                glosses=tuple(glosses),
                etymology=rec.get('etymology_text') or None,
                senses=tuple(senses),
            ))
            self._add_form(word, word, lexical)
            for form in rec.get('forms', []):
                if form.get('form') and not SKIP_FORM_TAGS & set(form.get('tags', [])):
                    self._add_form(form['form'], word, lexical)

    def candidates(self, word: str) -> list[str]:
        """Headwords this form belongs to (the Lemmatizer protocol)."""
        return list(self._forms.get(fold(word), []))

    def is_lexical(self, word: str) -> bool:
        """True when the form belongs to an ordinary word, not only to proper names."""
        return fold(word) in self._lexical

    def lookup(self, lemma: str) -> list[DictEntry]:
        return list(self._entries.get(fold(lemma), []))


GlosbeFetch = Callable[[str], list[str]]
ContextExplainer = Callable[[str, str], str | None]  # (lemma, sentence) -> gloss


class GlossResolver:
    def __init__(
        self,
        vocabulary: Vocabulary | None = None,
        dictionary: KaikkiDictionary | None = None,
        glosbe: GlosbeFetch | None = None,
        explainer: ContextExplainer | None = None,
        glosbe_delay: float = 0.0,
        max_glosses: int = 3,
    ):
        self.vocabulary = vocabulary
        self.dictionary = dictionary
        self.glosbe = glosbe
        self.explainer = explainer
        self.glosbe_delay = glosbe_delay
        self.max_glosses = max_glosses
        self._cache: dict[tuple[str, bool], Gloss | None] = {}
        self._glosbe_calls = 0

    def resolve(self, lemma: str, context: str = '', online: bool = True) -> Gloss | None:
        """
        The first gloss found; ``online=False`` skips Glosbe and the explainer. A
        dictionary gloss lists the senses ``context`` points to first. Glosbe is not used
        to rank senses: its top translation is no better a guess (ανάρτηση: suspension).
        """
        key = (fold(lemma), online)
        if key not in self._cache:
            self._cache[key] = self._resolve(lemma, context, online)
        return self._cache[key]

    def _resolve(self, lemma: str, context: str, online: bool) -> Gloss | None:
        if self.vocabulary is not None:
            info = self.vocabulary.lookup(lemma)
            if info.entry is not None and info.entry.gloss:
                return Gloss(info.entry.lemma, info.entry.gloss, SOURCE_DECK)

        if self.dictionary is not None:
            entries = self.dictionary.lookup(lemma)
            if not entries:
                for head in self.dictionary.candidates(lemma):
                    entries = self.dictionary.lookup(head)
                    if entries:
                        break
            if entries:
                first = entries[0]
                senses = rank_senses(entries, context)[: self.max_glosses]
                return Gloss(first.word, '; '.join(senses), SOURCE_WIKTIONARY, first.pos, first.etymology)

        if not online:
            return None

        if self.glosbe is not None:
            if self._glosbe_calls and self.glosbe_delay:
                time.sleep(self.glosbe_delay)
            self._glosbe_calls += 1
            try:
                translations = self.glosbe(lemma)
            except OSError:  # network failures (requests errors included) leave it unglossed
                translations = []
            if translations:
                return Gloss(lemma, ', '.join(translations[: self.max_glosses]), SOURCE_GLOSBE)

        if self.explainer is not None:
            text = self.explainer(lemma, context)
            if text:
                return Gloss(lemma, text, SOURCE_CONTEXT)
        return None
