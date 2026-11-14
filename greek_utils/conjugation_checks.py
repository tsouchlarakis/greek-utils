"""
Paradigm checks for a verb's conjugation table (greek-utils#19).

`verb_conjugations.json` was scraped from cooljugator.com and carries the site's own
errors: an aorist αυτοί that repeats εγώ, imperative columns holding the other aspect's
form. The checks here are the knowledge base's `paradigm_failures()` (its Greek deck
audit, knowledge-base#205), ported so `verb-flashcard` refuses a table that fails them.
They only catch what is wrong whatever the
verb, and "—" (not in use) never fails.

Plus one check from the issue: a first-person aorist εγώ that is not an aorist form.
"""

import re
import unicodedata

PERSONS = ('1sg', '2sg', '3sg', '1pl', '2pl', '3pl')
TENSE_PREFIXES = {
    'present': 'present_simple',
    'future': 'future_simple',
    'aorist': 'past_aorist',
    'imperfect': 'past_imperfect',
}
IMPERATIVE_PREFIXES = {
    'imperative_imperfective': 'imperative_imperfect_mood',
    'imperative_perfective': 'imperative_perfect_mood',
}
IMPERATIVE_PERSONS = ('2sg', '2pl')


def cell_key(tense: str, index: int) -> str:
    """The `verb_conjugations.json` key of a table cell, e.g. ('aorist', 5) → past_aorist_3pl."""
    if tense in TENSE_PREFIXES:
        return f'{TENSE_PREFIXES[tense]}_{PERSONS[index]}'
    return f'{IMPERATIVE_PREFIXES[tense]}_{IMPERATIVE_PERSONS[index]}'


def table_forms(conj: dict) -> dict[str, list[str]]:
    """A dataset conjugation as {tense: [cells]}, the shape the checks take."""
    forms = {tense: [conj.get(f'{prefix}_{p}', '') for p in PERSONS] for tense, prefix in TENSE_PREFIXES.items()}
    forms |= {
        tense: [conj.get(f'{prefix}_{p}', '') for p in IMPERATIVE_PERSONS]
        for tense, prefix in IMPERATIVE_PREFIXES.items()
    }
    return forms


def _strip_accents(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')


def _plain(form: str) -> str:
    return re.sub(r'[()]', '', _strip_accents(form).lower().strip())


def _used(value: str) -> bool:
    return bool(value) and value not in ('—', '-')


def _shared_prefix(a: str, b: str) -> int:
    a, b = _plain(re.sub(r'^(να|θα) ', '', a)), _plain(re.sub(r'^(να|θα) ', '', b))
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return n


def _aspect(form: str, present: str, future: str) -> str | None:
    """ "imperfective" when `form` shares more of its stem with the present than with the
    future (the perfective stem), "perfective" for the reverse, None on a tie (verbs whose
    two stems look alike, like διαφέρω)."""
    p, f = _shared_prefix(form, present), _shared_prefix(form, future)
    return 'imperfective' if p > f else 'perfective' if f > p else None


def paradigm_failures(forms: dict[str, list[str]]) -> list[tuple[str, int, str]]:
    """(tense, person index, reason) for each cell of `forms` (see `table_forms`) that
    fails a check: a future without θα, an aorist εγώ without -α, a past αυτοί that repeats
    εγώ or lacks its -ν, and imperative columns holding the other aspect's form (judged by
    which stem, present or future, the form shares more of)."""
    out: list[tuple[str, int, str]] = []

    def get(key: str) -> list[str]:
        return forms.get(key) or []

    for i, v in enumerate(get('future')):
        if _used(v) and not v.startswith('θα '):
            out.append(('future', i, 'future without θα'))
    # A first-person aorist ends in -α (or the learned -ην/-ον: απέστην, εύρον). Impersonal
    # verbs (βραδιάζει) list third-person forms in every row, so they are not checked.
    aorist, present = get('aorist'), get('present')
    first_person = bool(present) and re.search(r'(ω|μαι)$', _plain(present[0]))
    if first_person and aorist and _used(aorist[0]) and not re.search(r'(α|ην|ον)$', _plain(aorist[0])):
        out.append(('aorist', 0, 'εγώ not an aorist form'))
    for key in ('aorist', 'imperfect'):
        cells = get(key)
        if len(cells) == 6 and _used(cells[5]):
            if cells[5] == cells[0]:
                out.append((key, 5, 'αυτοί same as εγώ'))
            elif not re.search(r'νε?$', _plain(cells[5])):
                out.append((key, 5, 'αυτοί without -ν'))
    present, future = get('present'), get('future')
    imperf, perf = get('imperative_imperfective'), get('imperative_perfective')
    if len(present) != 6 or len(future) != 6 or len(imperf) != 2 or len(perf) != 2:
        return out
    passive = _plain(present[0]).endswith('μαι')
    for row, person in ((0, 1), (1, 4)):
        im, pf = imperf[row], perf[row]
        im_aspect = _aspect(im, present[person], future[person]) if _used(im) else None
        pf_aspect = _aspect(pf, present[person], future[person]) if _used(pf) else None
        perfective = re.sub(r'^θα ', '', future[person])
        pf_bad = _used(pf) and (
            (pf.startswith('να ') and pf_aspect != 'perfective')
            or (pf == present[person] and perfective != present[person])
            or (pf_aspect == 'imperfective' and im_aspect == 'perfective')
        )
        im_bad = _used(im) and im_aspect == 'perfective'
        # An active verb's imperfective εσύ ends in -ε/-α/-ει; -σου is a (made-up) passive.
        if (
            _used(im)
            and row == 0
            and not passive
            and not im.startswith('να ')
            and not re.search(r'(ε|α|ει)$', _plain(im))
        ):
            im_bad = True
        # Columns swapped: the perfective column holds the imperfective form and the
        # imperfective column a form that is not clearly imperfective.
        if pf_bad and _used(im) and im_aspect != 'imperfective':
            im_bad = True
        if im_bad:
            out.append(('imperative_imperfective', row, 'not an imperfective form'))
        if pf_bad:
            out.append(('imperative_perfective', row, 'present-stem form in the perfective column'))
    return out


def conjugation_failures(conj: dict) -> list[tuple[str, int, str]]:
    """`paradigm_failures` of a `verb_conjugations.json` conjugation."""
    return paradigm_failures(table_forms(conj))
