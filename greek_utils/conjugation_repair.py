"""
Repair the cells of `verb_conjugations.json` that fail the paradigm checks (greek-utils#19).

Each failing cell takes the form the kaikki.org Wiktionary extract gives for that verb,
voice, tense and person; without one, an αυτοί past that follows from the verb's own εγώ
(-α + ν: έγραψα → έγραψαν). Imperatives come from the source only: swapping the columns
back can pass the checks with a form that does not exist (φιγούρασου). A cell neither can
repair stays as it is, and `verb-flashcard` refuses that verb.

    python -m greek_utils.conjugation_repair --kaikki kaikki-el.jsonl [--conjugations-json PATH]
"""

import json
import re
from collections.abc import Iterable
from os.path import dirname, join

import click

from greek_utils.conjugation_checks import cell_key, conjugation_failures

DEFAULT_JSON = join(dirname(dirname(__file__)), 'verb_conjugations.json')
PERSON_TAGS = {
    '1sg': {'first-person', 'singular'},
    '2sg': {'second-person', 'singular'},
    '3sg': {'third-person', 'singular'},
    '1pl': {'first-person', 'plural'},
    '2pl': {'second-person', 'plural'},
    '3pl': {'third-person', 'plural'},
}
TENSE_TAGS = {
    'aorist': {'indicative', 'past', 'perfective'},
    'imperfect': {'indicative', 'imperfect', 'imperfective'},
    'imperative_imperfective': {'imperative', 'imperfective'},
    'imperative_perfective': {'imperative', 'perfective'},
}
SKIP_TAGS = {'archaic', 'dialectal', 'obsolete', 'dependent'}
# Used only when the source has no unmarked form (εισβάλλω's only εσύ imperatives are rare).
MARKED_TAGS = {'rare', 'informal', 'colloquial'}
GREEK_WORD = re.compile(r'^[Ͱ-Ͽἀ-῿]+$')
NOT_IN_USE = '—'


def _clean(form: str) -> str | None:
    """A kaikki form as a single word: superscript markers and a parenthesized variant
    dropped ("θέλουν² (θένε)" → θέλουν), "-" (not in use) as "—", None for anything else."""
    form = form.strip()
    if form in ('-', '‑', '—'):
        return NOT_IN_USE
    form = re.sub(r'\(.*?\)', '', form)
    form = re.sub(r'[²³¹⁰-₟]', '', form).strip()
    return form if GREEK_WORD.match(form) else None


class KaikkiVerbs:
    """Verb forms from a kaikki.org Greek extract, looked up by headword, voice, tense and person."""

    def __init__(self, records: Iterable[dict]):
        self._entries: dict[str, list[list[dict]]] = {}
        for rec in records:
            if rec.get('pos') == 'verb' and rec.get('lang_code', 'el') == 'el' and rec.get('word') and rec.get('forms'):
                self._entries.setdefault(rec['word'], []).append(rec['forms'])

    @classmethod
    def load(cls, path: str, words: set[str] | None = None) -> 'KaikkiVerbs':
        def records():
            with open(path, encoding='utf-8') as f:
                for line in f:
                    if '"verb"' not in line:
                        continue
                    rec = json.loads(line)
                    if words is None or rec.get('word') in words:
                        yield rec

        return cls(records())

    def __contains__(self, verb: str) -> bool:
        return verb in self._entries

    def form(self, verb: str, passive: bool, tense: str, person: str) -> str | None:
        """The first unmarked form for the cell, else the first rare or informal one;
        NOT_IN_USE when the source marks it "-"; None when the source has none."""
        want = TENSE_TAGS[tense] | PERSON_TAGS[person]
        voice = 'passive' if passive else 'active'
        for skip in (SKIP_TAGS | MARKED_TAGS, SKIP_TAGS):
            for forms in self._entries.get(verb, []):
                voiced = any({'active', 'passive'} & set(f.get('tags', [])) for f in forms)
                for f in forms:
                    tags = set(f.get('tags', []))
                    if not want <= tags or tags & skip or (voiced and voice not in tags):
                        continue
                    if tense in ('aorist', 'imperfect') and 'imperative' in tags:
                        continue
                    cleaned = _clean(f.get('form', ''))
                    if cleaned is not None:
                        return cleaned
        return None


def _is_passive(conj: dict) -> bool:
    return conj.get('present_simple_1sg', '').endswith(('μαι', 'μαί'))


def _fix_cells(conj: dict, failures, verb: str, kaikki: KaikkiVerbs) -> dict:
    """A copy of `conj` with the failing cells replaced where a source has a form."""
    fixed = dict(conj)
    passive = _is_passive(conj)
    failing = {(tense, i) for tense, i, _ in failures}
    # The aorist εγώ first: the derived αυτοί below builds on it.
    if ('aorist', 0) in failing:
        form = kaikki.form(verb, passive, 'aorist', '1sg')
        if form and form != NOT_IN_USE:
            fixed[cell_key('aorist', 0)] = form
    for tense in ('aorist', 'imperfect'):
        if (tense, 5) not in failing:
            continue
        form = kaikki.form(verb, passive, tense, '3pl')
        first = fixed[cell_key(tense, 0)]
        if (not form or form == NOT_IN_USE) and first.endswith(('α', 'ά')):
            form = first + 'ν'
        if form and form != NOT_IN_USE:
            fixed[cell_key(tense, 5)] = form
    for row, person in enumerate(('2sg', '2pl')):
        if not {('imperative_imperfective', row), ('imperative_perfective', row)} & failing:
            continue
        imperf = kaikki.form(verb, passive, 'imperative_imperfective', person)
        perf = kaikki.form(verb, passive, 'imperative_perfective', person)
        im_key, pf_key = cell_key('imperative_imperfective', row), cell_key('imperative_perfective', row)
        if imperf and perf:
            fixed[im_key], fixed[pf_key] = imperf, perf
    return fixed


def repair(data: dict, kaikki: KaikkiVerbs) -> tuple[dict, dict[str, list[str]]]:
    """(repaired dataset, {verb: changed keys}). A verb's cells change only when the
    repaired table fails fewer checks than before."""
    out, changes = {}, {}
    for verb, entry in data.items():
        conj = entry.get('conjugation') or {}
        failures = conjugation_failures(conj)
        if failures:
            fixed = _fix_cells(conj, failures, verb, kaikki)
            if len(conjugation_failures(fixed)) < len(failures):
                changes[verb] = sorted(k for k in fixed if fixed[k] != conj.get(k))
                entry = {**entry, 'conjugation': fixed}
        out[verb] = entry
    return out, changes


def failing_verbs(data: dict) -> list[str]:
    return [verb for verb, entry in data.items() if conjugation_failures(entry.get('conjugation') or {})]


def dump(data: dict, path: str) -> None:
    """Write the dataset in the format the scraper's file has (4-space indent, UTF-8, no final newline)."""
    with open(path, 'w', encoding='utf-8') as f:
        f.write(json.dumps(data, indent=4, ensure_ascii=False))


@click.command()
@click.option('--kaikki', 'kaikki_path', required=True, help='kaikki.org Greek extract (JSON lines).')
@click.option('--conjugations-json', default=DEFAULT_JSON, help='Dataset to repair in place.')
def main(kaikki_path: str, conjugations_json: str) -> None:
    with open(conjugations_json, encoding='utf-8') as f:
        data = json.load(f)
    before = failing_verbs(data)
    kaikki = KaikkiVerbs.load(kaikki_path, words=set(before))
    repaired, changes = repair(data, kaikki)
    after = failing_verbs(repaired)
    dump(repaired, conjugations_json)
    print(f'verbs failing a check: {len(before)} before, {len(after)} after; {len(changes)} verbs repaired')


if __name__ == '__main__':
    main()
