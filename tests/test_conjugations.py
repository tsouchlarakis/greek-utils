"""
Paradigm checks and the kaikki repair of verb_conjugations.json (greek-utils#19).

Known forms come from the kaikki.org Wiktionary extract; the broken cells are the ones
cooljugator.com served and the scraper copied (εργάζομαι's aorist αυτοί εργάστηκα, θέλω's
imperatives θέλσου / να θέλεις).
"""

import json
from os.path import dirname, join

import pytest
from click.testing import CliRunner

from greek_utils.cli import cli
from greek_utils.conjugation_checks import conjugation_failures, paradigm_failures
from greek_utils.conjugation_repair import KaikkiVerbs, failing_verbs, repair

ROOT = dirname(dirname(__file__))
FIXTURES = join(dirname(__file__), 'fixtures')
# Verbs whose table fails a check after the repair (637 before it). The repair has no
# source for their cells, so verb-flashcard refuses them. Lower this when a repair lands;
# never raise it.
FAILING_CEILING = 440


@pytest.fixture(scope='module')
def data() -> dict:
    with open(join(ROOT, 'verb_conjugations.json'), encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture(scope='module')
def kaikki() -> KaikkiVerbs:
    return KaikkiVerbs.load(join(FIXTURES, 'kaikki-verbs.jsonl'))


def imperatives(conj: dict) -> tuple:
    return (
        conj['imperative_imperfect_mood_2sg'],
        conj['imperative_perfect_mood_2sg'],
        conj['imperative_imperfect_mood_2pl'],
        conj['imperative_perfect_mood_2pl'],
    )


# The scraped cells, put back over the repaired row.
SCRAPED = {
    'εργάζομαι': {
        'past_aorist_3pl': 'εργάστηκα',
        'imperative_imperfect_mood_2sg': 'εργάσου',
        'imperative_perfect_mood_2sg': 'να εργάζεσαι',
        'imperative_imperfect_mood_2pl': 'εργαστείτε',
        'imperative_perfect_mood_2pl': 'εργάζεστε',
    },
    'θέλω': {
        'past_aorist_3pl': 'θέλησα',
        'imperative_imperfect_mood_2sg': 'θέλσου',
        'imperative_perfect_mood_2sg': 'να θέλεις',
        'imperative_imperfect_mood_2pl': 'θελήστε',
        'imperative_perfect_mood_2pl': 'θέλετε',
    },
    'συμβουλεύω': {'past_imperfect_3pl': 'συμβόυλευ', 'past_aorist_3pl': 'συμβούλεψα'},
    # Not in the fixture: only the derivable αυτοί (εγώ + ν) can be repaired.
    'φιγουράρω': {'past_aorist_3pl': 'φιγουράρισα'},
}


def scraped(data: dict, verb: str) -> dict:
    return {**data[verb]['conjugation'], **SCRAPED[verb]}


@pytest.mark.parametrize('verb', sorted(SCRAPED))
def test_scraped_cells_fail_the_checks(data, verb):
    assert conjugation_failures(scraped(data, verb))


def test_dataset_has_the_known_forms(data):
    erg, thelo = data['εργάζομαι']['conjugation'], data['θέλω']['conjugation']
    assert erg['past_aorist_3pl'] == 'εργάστηκαν'
    assert imperatives(erg) == ('—', 'εργάσου', 'εργάζεστε', 'εργαστείτε')
    assert thelo['past_aorist_3pl'] == 'θέλησαν'
    assert imperatives(thelo) == ('θέλε', 'θέλησε', 'θέλετε', 'θελήστε')
    assert data['οργανώνω']['conjugation']['past_aorist_3pl'] == 'οργάνωσαν'
    assert data['συμβουλεύω']['conjugation']['past_imperfect_3pl'] == 'συμβούλευαν'
    for verb in ('εργάζομαι', 'θέλω', 'οργανώνω', 'συμβουλεύω'):
        assert conjugation_failures(data[verb]['conjugation']) == []


def test_repair_takes_the_source_forms(data, kaikki):
    broken = {verb: {'conjugation': scraped(data, verb), 'example_usages': {}} for verb in SCRAPED}
    repaired, changes = repair(broken, kaikki)
    erg, thelo = repaired['εργάζομαι']['conjugation'], repaired['θέλω']['conjugation']
    assert erg['past_aorist_3pl'] == 'εργάστηκαν'
    assert imperatives(erg) == ('—', 'εργάσου', 'εργάζεστε', 'εργαστείτε')
    assert thelo['past_aorist_3pl'] == 'θέλησαν'
    assert imperatives(thelo) == ('θέλε', 'θέλησε', 'θέλετε', 'θελήστε')
    assert repaired['συμβουλεύω']['conjugation']['past_imperfect_3pl'] == 'συμβούλευαν'
    assert repaired['φιγουράρω']['conjugation']['past_aorist_3pl'] == 'φιγουράρισαν'
    assert set(changes) == set(SCRAPED)
    assert failing_verbs(repaired) == ['φιγουράρω']  # its imperatives have no source


def test_repair_never_invents_an_imperative(data, kaikki):
    """Swapping φιγουράρω's columns would pass the checks with φιγούρασου, which is not a
    form; with no source the imperatives stay as scraped and the verb stays failing."""
    conj = scraped(data, 'φιγουράρω')
    repaired, _ = repair({'φιγουράρω': {'conjugation': conj, 'example_usages': {}}}, kaikki)
    assert imperatives(repaired['φιγουράρω']['conjugation']) == imperatives(conj)


def test_repair_leaves_passing_verbs_alone(data, kaikki):
    passing = {verb: data[verb] for verb in ('θέλω', 'οργανώνω')}
    repaired, changes = repair(passing, kaikki)
    assert repaired == passing and changes == {}


def test_source_rare_form_only_without_an_unmarked_one(kaikki):
    assert kaikki.form('εισβάλλω', False, 'imperative_imperfective', '2sg') == 'είσβαλλε'  # tagged rare
    assert kaikki.form('θέλω', False, 'aorist', '3pl') == 'θέλησαν'
    assert kaikki.form('θέλω', False, 'imperfect', '3pl') == 'ήθελαν'
    assert kaikki.form('άγνωστο', False, 'aorist', '3pl') is None


def test_checks_accept_not_in_use_and_impersonal_verbs():
    forms = {
        'present': ['εργάζομαι', 'εργάζεσαι', 'εργάζεται', 'εργαζόμαστε', 'εργάζεστε', 'εργάζονται'],
        'future': ['θα εργαστώ', 'θα εργαστείς', 'θα εργαστεί', 'θα εργαστούμε', 'θα εργαστείτε', 'θα εργαστούν'],
        'aorist': ['εργάστηκα', 'εργάστηκες', 'εργάστηκε', 'εργαστήκαμε', 'εργαστήκατε', 'εργάστηκαν'],
        'imperfect': ['εργαζόμουν', 'εργαζόσουν', 'εργαζόταν', 'εργαζόμασταν', 'εργαζόσασταν', 'εργάζονταν'],
        'imperative_imperfective': ['—', 'εργάζεστε'],
        'imperative_perfective': ['εργάσου', 'εργαστείτε'],
    }
    assert paradigm_failures(forms) == []
    impersonal = {'present': ['χιονίζει'] * 6, 'aorist': ['χιόνισε'] * 5 + ['χιόνισαν']}
    assert paradigm_failures(impersonal) == []
    assert paradigm_failures({'present': ['αιτώ'] * 6, 'aorist': ['αιτούμαι'] + [''] * 5}) == [
        ('aorist', 0, 'εγώ not an aorist form')
    ]
    assert paradigm_failures({'future': ['εργαστώ']}) == [('future', 0, 'future without θα')]


def test_whole_dataset_failures_only_fall(data):
    assert len(failing_verbs(data)) <= FAILING_CEILING


def test_verb_flashcard_refuses_a_failing_table(data):
    verb = next(v for v in failing_verbs(data) if v == 'φιγουράρω')
    result = CliRunner().invoke(cli, ['verb-flashcard', '--verb', verb, '--stdout'])
    assert result.exit_code != 0
    assert '<table' not in result.output
    assert 'fails paradigm checks' in result.output


def test_verb_flashcard_emits_the_repaired_table():
    result = CliRunner().invoke(cli, ['verb-flashcard', '--verb', 'θέλω', '--stdout'])
    assert result.exit_code == 0, result.output
    assert '<table' in result.output and 'θέλησαν' in result.output and 'θέλσου' not in result.output


def test_template_labels_are_accented():
    with open(join(ROOT, 'greek_utils', 'templates', 'verb_flashcard_template.html'), encoding='utf-8') as f:
        template = f.read()
    for label in ('>εγώ<', '>εσύ<', '>αυτ(ός/ή/ό)<', '>εμείς<', '>εσείς<', '>αυτ(οί/ές/ά)<'):
        assert label in template
    for label in ('>εγω<', '>εσυ<', '>αυτ(ος/η/ο)<'):
        assert label not in template
