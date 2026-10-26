"""Vocabulary states, targets, adaptation checks, glosses and ``reader build``, on synthetic fixtures."""

import json
import unicodedata
from pathlib import Path

import pytest
from click.testing import CliRunner

from greek_utils.cli import cli
from greek_utils.reader.adapt import (
    ORIGIN_ADAPTER,
    ORIGIN_EXCERPT,
    ORIGIN_FALLBACK,
    Rules,
    adapt,
    build_prompt,
    check_adaptation,
    excerpt,
)
from greek_utils.reader.article import load, parse_text
from greek_utils.reader.build import build
from greek_utils.reader.gloss import SOURCE_DECK, SOURCE_GLOSBE, SOURCE_WIKTIONARY, GlossResolver, KaikkiDictionary
from greek_utils.reader.targets import select_targets, targets_used
from greek_utils.reader.text import accent_position, fold, sentences, strict, tokenize
from greek_utils.reader.vocab import (
    FUNCTION,
    NAME,
    NEW,
    NUMBER,
    VocabEntry,
    Vocabulary,
    headword,
    headword_from_card_field,
    new_ratio,
)

FIXTURES = Path(__file__).parent / 'fixtures'
ARTICLE_HTML = FIXTURES / 'article.html'
ADAPTED = FIXTURES / 'adapted.txt'
VOCAB = FIXTURES / 'vocab.json'
KAIKKI = FIXTURES / 'kaikki-mini.jsonl'


@pytest.fixture(scope='module')
def dictionary():
    return KaikkiDictionary.load(KAIKKI)


@pytest.fixture(scope='module')
def vocabulary(dictionary):
    return Vocabulary.from_file(VOCAB, lemmatizer=dictionary)


@pytest.fixture(scope='module')
def article():
    return load(str(ARTICLE_HTML))


@pytest.fixture(scope='module')
def adapted():
    return ADAPTED.read_text(encoding='utf-8')


# Text


def test_fold_and_strict():
    assert fold('Πότε') == fold('ποτέ') == fold('ΠΟΤΕ') == 'ποτε'
    assert strict('Πότε') != strict('ποτέ')
    assert fold('μυς') == fold('μυσ')
    assert strict('Ρολόι') == strict('ρολοϊ'.replace('ϊ', 'ι')) or fold('ρολόι') == fold('ρολοϊ')
    assert accent_position('πότε') == 1 and accent_position('ποτέ') == 3 and accent_position('ΠΟΤΕ') is None


def test_tokenize_numbers_elision_and_sentences():
    text = 'Πήρε 14.333 βαθμούς. Απ\' την κόλαση; «Ναι», είπε: Ήταν 35χρονος.'
    toks = tokenize(text)
    assert [t.text for t in toks] == [
        'Πήρε', '14.333', 'βαθμούς', "Απ'", 'την', 'κόλαση', 'Ναι', 'είπε', 'Ήταν', '35χρονος']
    assert [t.kind for t in toks].count('number') == 2
    assert [t.initial for t in toks] == [True, False, False, True, False, False, True, False, True, False]
    assert len(sentences(text)) == 3


# Vocabulary


def test_headwords():
    assert headword('η δοκιμασία') == 'δοκιμασία'
    assert headword('ορεινός, -ή, -ό') == 'ορεινός'
    assert headword('μόλις και μετά βίας') == 'μόλις και μετά βίας'
    assert headword_from_card_field('ο κρίκος<br><br><i>rings</i> example') == 'κρίκος'
    assert headword_from_card_field('<b>σαφής, -ής, -ές</b><br>table') == 'σαφής'


def test_lookup_inflected_forms(vocabulary):
    assert vocabulary.lookup('ορεινού').lemma == 'ορεινός'
    assert vocabulary.lookup('ορεινού').state == 'due'
    assert vocabulary.lookup('ξηρασίας').lemma == 'ξηρασία'
    assert vocabulary.lookup('δυσκολεύτηκαν').lemma == 'δυσκολεύομαι'  # prefix stem
    assert vocabulary.lookup('γήπεδο').state == 'lapsed'
    assert vocabulary.lookup('είπε').state == 'known'  # kaikki form → λέω, in the frequent list
    assert vocabulary.lookup('είπε').lemma == 'λέω'
    assert vocabulary.lookup('λαούτα').state == NEW
    assert vocabulary.lookup('λαούτα').lemma == 'λαούτο'


def test_strongest_state_wins():
    v = Vocabulary([VocabEntry('η σοδειά', 'known'), VocabEntry('σοδειά', 'due')])
    assert v.lookup('σοδειάς').state == 'due'
    with pytest.raises(ValueError):
        Vocabulary([VocabEntry('σοδειά', 'sometimes')])


def test_annotate_kinds(vocabulary):
    kinds = {t.text: info.state for t, info in vocabulary.annotate(
        'Ο Νίκος Παπαδάκης είπε ότι 2.000 επισκέπτες ήρθαν από το Partanen.')}
    assert kinds['Ο'] == FUNCTION and kinds['ότι'] == FUNCTION
    assert kinds['Νίκος'] == NAME and kinds['Παπαδάκης'] == NAME and kinds['Partanen'] == NAME
    assert kinds['2.000'] == NUMBER
    assert kinds['επισκέπτες'] == 'known'


def test_new_ratio_groups_forms(vocabulary):
    ratio, new, total = new_ratio(vocabulary.annotate('Τα κάστανα και το κάστανο. Το σχολείο.'))
    assert new == ['κασταν'] and total == 2 and ratio == 0.5


# Targets


def test_targets_follow_quotas_and_prefer_the_article(vocabulary, article):
    targets = select_targets(vocabulary, article.text)
    by_state = {}
    for t in targets:
        by_state.setdefault(t.state, []).append(t.lemma)
    # καταιγίδα is first in the due list but absent from the article, so six present
    # due words win; ορεινός is the seventh present one and misses the quota.
    assert by_state['due'] == ['σοδειά', 'ξηρασία', 'διοργανωτής', 'εκδήλωση', 'επισκευή', 'λαογραφικός']
    assert by_state['recent'] == ['έσοδα', 'παραγωγός', 'εργαστήριο', 'ψητός']
    assert by_state['lesson'] == ['σύλλογος', 'δυσκολεύομαι', 'συνάντηση']
    assert 'γήπεδο' not in [t.lemma for t in targets]  # lapsed and known words are not targets
    assert all(t.in_article for t in targets)
    assert targets[0].gloss == 'harvest, crop'


def test_absent_words_fill_the_quota_when_needed(vocabulary):
    targets = select_targets(vocabulary, 'Ένα κείμενο χωρίς τις λέξεις.')
    assert next(t.lemma for t in targets if t.state == 'due') == 'καταιγίδα'
    assert not any(t.in_article for t in targets)


# Checks


def test_supplied_adaptation_passes_every_check(vocabulary, article, adapted):
    targets = select_targets(vocabulary, article.text)
    report = check_adaptation(adapted, article.text, targets, vocabulary)
    assert report.passed, report.failures()
    assert report.get('length').value == 150  # the title line is not counted
    assert 0.06 <= report.get('new_ratio').value <= 0.14
    assert len(report.get('targets').value) >= 8


@pytest.mark.parametrize('edit, failing', [
    (lambda t: t.replace('2.000', '3.000'), 'numbers'),
    (lambda t: t.replace('Παπαδάκης, είπε', 'Μανωλάκης, είπε'), 'names'),
    (lambda t: t.replace('δεν το έβαλαν κάτω', 'δεν σταμάτησαν'), 'quotes'),
    (lambda t: t + '\n\n' + ' '.join(['Η γιορτή ήταν ωραία.'] * 6), 'length'),
    (lambda t: t.replace('. Η εκδήλωση ξεκινά', ', και η εκδήλωση ξεκινά').replace(
        'χωριού.\n\nΦέτος', 'χωριού, ενώ φέτος'), 'sentence_length'),
    (lambda t: t.replace('λύρα και λαούτο', 'μαντολίνο, σαντούρι, ασκομαντούρα, βιολί, '
                                            'τουμπερλέκι και νταούλι'), 'new_ratio'),
    # Swap five target words for words that are already known.
    (lambda t: t.replace('σοδειά', 'χρονιά').replace('ξηρασίας', 'καλοκαιριού').replace(
        'διοργανωτές', 'κάτοικοι').replace('εκδήλωση', 'γιορτή').replace('επισκευή', 'μουσική'),
     'targets'),
])
def test_each_check_catches_its_failure(vocabulary, article, adapted, edit, failing):
    targets = select_targets(vocabulary, article.text)
    report = check_adaptation(edit(adapted), article.text, targets, vocabulary)
    failed = [r.name for r in report.results if not r.passed]
    assert failed == [failing], report.failures()


def test_excerpt_stays_within_length(article):
    text = excerpt(article.text)
    n = len(tokenize(text))
    assert Rules().prompt_min_words <= n <= Rules().max_words
    assert text.startswith('Για εικοσιπέμπτη συνεχή χρονιά')
    assert text.rstrip().endswith('.')


# Adapter


def test_prompt_lists_targets_and_rules(vocabulary, article):
    targets = select_targets(vocabulary, article.text)
    prompt = build_prompt(article, targets, failures=['length: 200 words'])
    assert 'CEFR B2' in prompt and '140-160 words' in prompt
    assert '  - σοδειά' in prompt and 'at least 8 of these target words' in prompt
    assert 'failed these checks' in prompt and '- length: 200 words' in prompt
    assert article.text in prompt


def test_adapter_retries_once_with_the_failures(vocabulary, article, adapted):
    targets = select_targets(vocabulary, article.text)
    prompts = []

    def adapter(prompt):
        prompts.append(prompt)
        return adapted.replace('2.000', '3.000') if len(prompts) == 1 else adapted

    result = adapt(article, targets, vocabulary, adapter)
    assert result.origin == ORIGIN_ADAPTER and result.report.passed
    assert len(prompts) == 2
    assert 'failed these checks' not in prompts[0]
    assert 'numbers: not in the source: 3.000' in prompts[1]
    assert result.attempts[0]['failures'] and not result.attempts[1]['failures']


def test_two_failures_fall_back_to_an_excerpt(vocabulary, article):
    targets = select_targets(vocabulary, article.text)
    result = adapt(article, targets, vocabulary, lambda prompt: 'Πολύ μικρό κείμενο.')
    assert result.origin == ORIGIN_FALLBACK
    assert result.text == excerpt(article.text)
    assert len(result.attempts) == 2


def test_no_adapter_gives_the_checked_excerpt(vocabulary, article):
    result = adapt(article, select_targets(vocabulary, article.text), vocabulary)
    assert result.origin == ORIGIN_EXCERPT and result.report.results


# Glosses


def test_kaikki_index(dictionary):
    assert dictionary.candidates('κάστανα') == ['κάστανο']  # form-of entry
    assert dictionary.candidates('έβαλαν') == ['βάζω']  # forms table
    assert dictionary.candidates('léo') == []  # romanizations are not forms
    entries = dictionary.lookup('κάστανο')
    assert len(entries) == 1 and entries[0].glosses == ('chestnut',)  # the non-Greek entry is skipped


def test_gloss_order(vocabulary, dictionary):
    calls = []

    def glosbe(word):
        calls.append(word)
        return ['to paint', 'to draw', 'to sketch', 'to depict'] if word.startswith('ζωγραφ') else []

    resolver = GlossResolver(vocabulary, dictionary, glosbe=glosbe)
    deck = resolver.resolve('σοδειά')
    assert (deck.source, deck.text) == (SOURCE_DECK, 'harvest, crop')  # deck beats Wiktionary
    lyra = resolver.resolve('λύρα')
    assert lyra.source == SOURCE_WIKTIONARY and lyra.text == 'lyre; Cretan lyra, a bowed string instrument'
    chestnut = resolver.resolve('κάστανα')
    assert (chestnut.lemma, chestnut.etymology) == ('κάστανο', 'From Ancient Greek κάστανον.')
    paint = resolver.resolve('ζωγραφίσουν')
    assert paint.source == SOURCE_GLOSBE and paint.text == 'to paint, to draw, to sketch'
    assert resolver.resolve('παρκάρουν', online=False) is None
    assert resolver.resolve('παρκάρουν') is None
    resolver.resolve('ζωγραφίσουν')
    assert calls == ['ζωγραφίσουν', 'παρκάρουν']  # cached, and never called offline


def test_glosbe_errors_leave_the_word_unglossed(vocabulary):
    def broken(word):
        raise ConnectionError('offline')
    assert GlossResolver(vocabulary, glosbe=broken).resolve('ζωγραφίζω') is None


# Article


def test_article_html(article):
    assert article.title == 'Γιορτή του κάστανου στον Ασπρόλακκο'
    assert article.outlet == 'Παράδειγμα Ειδήσεων'
    assert article.author == 'Συντακτική ομάδα'
    assert article.published == '2026-10-24T08:00:00+03:00'
    assert article.url == 'https://news.example.org/topika/giorti-kastanou'
    assert article.text.count('\n\n') == 4  # five paragraphs; nav, figure, footer dropped
    assert 'Φωτογραφία αρχείου' not in article.text and 'δικαιώματα' not in article.text


def test_article_plain_text():
    a = parse_text('Τίτλος\n\nΠρώτη παράγραφος.\n\nΔεύτερη.')
    assert a.title == 'Τίτλος' and a.text == 'Πρώτη παράγραφος.\n\nΔεύτερη.'
    assert parse_text('Μόνο κείμενο.').title == ''


# Build


def test_build_marks_tokens_and_glosses(vocabulary, dictionary, article, adapted):
    resolver = GlossResolver(vocabulary, dictionary, glosbe=lambda w: [])
    result = build(article, vocabulary, resolver=resolver, supplied_text=adapted)
    assert result['adaptation']['origin'] == 'supplied'
    assert result['adaptation']['checks']['passed']
    tokens = {t['text']: t for t in result['tokens']}
    assert tokens['σοδειά']['target'] and tokens['σοδειά']['state'] == 'due'
    assert tokens['λαούτο']['state'] == NEW and not tokens['λαούτο']['target']
    assert tokens['Παπαδάκης']['state'] == NAME
    assert result['glosses']['σοδειά']['source'] == SOURCE_DECK
    assert result['glosses']['λαούτο']['source'] == SOURCE_WIKTIONARY
    assert 'Παπαδάκης' not in result['glosses']
    assert result['source']['outlet'] == 'Παράδειγμα Ειδήσεων' and 'text' not in result['source']
    first = result['tokens'][0]
    assert adapted[first['start']:first['end']] == first['text']


def test_cli_build(tmp_path):
    out = tmp_path / 'build.json'
    res = CliRunner().invoke(cli, [
        'reader', 'build', str(ARTICLE_HTML), '--vocab', str(VOCAB), '--kaikki', str(KAIKKI),
        '--adapted', str(ADAPTED), '--no-glosbe', '--out', str(out), '--strict',
    ])
    assert res.exit_code == 0, res.output
    data = json.loads(out.read_text(encoding='utf-8'))
    assert data['adaptation']['checks']['passed']
    assert len(data['targets']) == 13
    assert data['glosses']['κάστανο']['text'] == 'chestnut'


def test_cli_build_strict_fails_on_a_bad_text(tmp_path):
    bad = tmp_path / 'bad.txt'
    bad.write_text('Πολύ μικρό κείμενο.', encoding='utf-8')
    res = CliRunner().invoke(cli, [
        'reader', 'build', str(ARTICLE_HTML), '--vocab', str(VOCAB), '--adapted', str(bad),
        '--no-glosbe', '--out', str(tmp_path / 'o.json'), '--strict',
    ])
    assert res.exit_code == 1
    assert 'FAIL length' in res.output


def test_cli_build_with_adapter_module(tmp_path, monkeypatch):
    module = tmp_path / 'fake_adapter.py'
    module.write_text(
        'from pathlib import Path\n'
        f'TEXT = Path({str(ADAPTED)!r}).read_text(encoding="utf-8")\n'
        'def adapt(prompt):\n    return TEXT\n',
        encoding='utf-8')
    monkeypatch.syspath_prepend(str(tmp_path))
    res = CliRunner().invoke(cli, [
        'reader', 'build', str(ARTICLE_HTML), '--vocab', str(VOCAB), '--kaikki', str(KAIKKI),
        '--adapter', 'fake_adapter:adapt', '--no-glosbe', '--out', str(tmp_path / 'o.json'),
    ])
    assert res.exit_code == 0, res.output
    assert 'origin: adapter; checks passed' in res.output


# Review fixes (PR #13)


def nfd(text: str) -> str:
    return unicodedata.normalize('NFD', text)


def test_decomposed_text_checks_the_same_as_precomposed(vocabulary, article, adapted):
    targets = select_targets(vocabulary, article.text)
    plain = check_adaptation(adapted, article.text, targets, vocabulary)
    decomposed = check_adaptation(nfd(adapted), nfd(article.text), targets, vocabulary)
    assert decomposed.passed, decomposed.failures()
    assert decomposed.get('length').value == plain.get('length').value == 150
    assert decomposed.get('new_ratio').value == plain.get('new_ratio').value
    assert decomposed.get('targets').value == plain.get('targets').value
    assert [len(tokenize(nfd(adapted)))] == [len(tokenize(adapted))]


@pytest.mark.parametrize('edit, failing', [
    # An unseen name opening a sentence is still a name.
    (lambda t: t.replace('Φέτος η σοδειά', 'Μανωλάκης, η σοδειά'), ['names']),
    # A surname that merely starts with a source adjective is not the source name.
    (lambda t: t.replace('Νίκος Παπαδάκης', 'Νίκος Παραδοσιακόπουλος'), ['names']),
    # The title is held to the same factual checks as the body.
    (lambda t: t.replace('Η γιορτή του κάστανου', 'Ο Μανωλάκης κέρδισε 999 ευρώ σήμερα', 1),
     ['numbers', 'names']),
    # A quantity rewritten in words is not verified.
    (lambda t: t.replace('850 μέτρα', 'χίλια μέτρα'), ['numbers']),
    (lambda t: t.replace('850 μέτρα', 'οκτακόσια πενήντα μέτρα'), ['numbers']),
    # Inflected cardinals and ordinals are spelled-out quantities too.
    (lambda t: t.replace('στα 850 μέτρα', 'σε υψόμετρο χιλίων μέτρων'), ['numbers']),
    (lambda t: t.replace('πάνω από 2.000 επισκέπτες', 'πάνω από διακοσίους επισκέπτες'), ['numbers']),
    (lambda t: t.replace('εικοσιπέμπτη', 'τριακοστή'), ['numbers']),
    # A clipped word is not a verbatim quotation.
    (lambda t: t.replace('δεν το έβαλαν κάτω', 'δεν το έβαλαν κάτ'), ['quotes']),
])
def test_review_bypasses_are_caught(vocabulary, article, adapted, edit, failing):
    targets = select_targets(vocabulary, article.text)
    report = check_adaptation(edit(adapted), article.text, targets, vocabulary)
    assert [r.name for r in report.results if not r.passed] == failing, report.failures()


@pytest.mark.parametrize('edit', [
    lambda t: t.replace('δεν το έβαλαν κάτω', 'δεν το έβαλαν'),  # a verbatim excerpt
    lambda t: t.replace('Νίκος Παπαδάκης', 'Νίκου Παπαδάκη'),  # inflected source name
    lambda t: t.replace('Φέτος η σοδειά', 'Η σοδειά φέτος'),
    lambda t: t.replace('Η γιορτή του κάστανου', 'Γιορτή του κάστανου στον Ασπρόλακκο', 1),
])
def test_legitimate_variants_still_pass(vocabulary, article, adapted, edit):
    targets = select_targets(vocabulary, article.text)
    report = check_adaptation(edit(adapted), article.text, targets, vocabulary)
    for name in ('numbers', 'names', 'quotes'):
        assert report.get(name).passed, report.failures()


def test_the_title_is_checked_against_the_source_title(vocabulary):
    report = check_adaptation('Ο Παπαδάκης στον Ασπρόλακκο\n\nΚείμενο.', 'Κείμενο χωρίς ονόματα.', [],
                              vocabulary, source_title='Ο Παπαδάκης στον Ασπρόλακκο')
    assert report.get('names').passed
    report = check_adaptation('Ο Παπαδάκης στον Ασπρόλακκο\n\nΚείμενο.', 'Κείμενο χωρίς ονόματα.', [],
                              vocabulary)
    assert not report.get('names').passed


def test_spelled_out_numbers_must_come_from_the_source(vocabulary):
    def numbers(text, source):
        return check_adaptation(text, source, [], vocabulary).get('numbers')

    assert numbers('Ήρθαν δύο φίλοι.', 'Ήρθαν δύο φίλοι.').passed
    assert not numbers('Ήρθαν τρεις φίλοι.', 'Ήρθαν δύο φίλοι.').passed
    assert not numbers('Ήρθαν εικοσιπέντε φίλοι.', 'Ήρθαν δύο φίλοι.').passed
    assert numbers('Ήρθε ένα παιδί.', 'Ήρθε το παιδί.').passed  # ένα is the article here
    assert numbers('Το κόμμα μίλησε.', 'Ο πρόεδρος μίλησε.').passed  # κόμμα is a party


def test_inflected_teens_are_spelled_out_numbers(article, adapted, vocabulary):
    targets = select_targets(vocabulary, article.text)
    assert check_adaptation(adapted, article.text, targets, vocabulary).get('numbers').passed
    for teen in ('δεκατριών', 'δεκατεσσάρων', 'δεκατρείς', 'δεκατέσσερις', 'δεκατρία', 'δεκατέσσερα'):
        edited = adapted.replace('στα 850 μέτρα', f'σε υψόμετρο {teen} μέτρων')
        assert edited != adapted
        report = check_adaptation(edited, article.text, targets, vocabulary)
        assert not report.get('numbers').passed, teen
        assert teen in report.get('numbers').value, teen


def test_a_weekday_is_checked_across_its_cases_as_a_name(article, adapted, vocabulary):
    targets = select_targets(vocabulary, article.text)
    source = article.text.replace('το Σάββατο στις 6', 'το βράδυ της Τρίτης στις 6')
    assert source != article.text

    def failed(day):
        edited = adapted.replace('το Σάββατο στις 6', f'{day} στις 6')
        assert edited != adapted
        return [r.name for r in check_adaptation(edited, source, targets, vocabulary).results if not r.passed]

    assert failed('την Τρίτη') == []
    assert failed('της Τρίτης') == []
    assert failed('την Πέμπτη') == ['names']  # a changed weekday is a name that is not in the source
    assert failed('την Τετάρτη') == ['names']
    # A weekday absent from the source is a name, not a number.
    absent = adapted.replace('το Σάββατο στις 6', 'την Τρίτη στις 6')
    report = check_adaptation(absent, article.text, targets, vocabulary)
    assert [r.name for r in report.results if not r.passed] == ['names']


def test_a_lowercase_ordinal_is_checked_even_when_its_weekday_is_in_the_source(article, adapted, vocabulary):
    targets = select_targets(vocabulary, article.text)
    source = article.text.replace('το Σάββατο στις 6', 'το βράδυ της Τρίτης στις 6')
    edited = adapted.replace('το Σάββατο στις 6', 'την Τρίτη στις 6').replace('εικοσιπέμπτη', 'τρίτη')
    assert edited != adapted and 'τρίτη χρονιά' in edited
    report = check_adaptation(edited, source, targets, vocabulary)
    assert not report.get('numbers').passed  # third year instead of twenty-fifth year
    assert 'τρίτη' in report.get('numbers').value or 'τρίτη' in (report.get('numbers').warning or '')
    assert report.get('names').passed  # the capitalized Τρίτη is still supported by the source


def test_quotation_must_match_whole_words(vocabulary):
    def quotes(text, source):
        return check_adaptation(text, source, [], vocabulary).get('quotes').passed

    source = 'Είπε: «Δεν το έβαλαν κάτω».'
    assert quotes('Είπε: «Δεν το έβαλαν κάτω».', source)
    assert quotes('Είπε: «το έβαλαν».', source)
    assert not quotes('Είπε: «το έβαλαν κάτ».', source)
    assert not quotes('Είπε: «εν το έβαλαν».', source)
    assert quotes(nfd('Είπε: «Δεν το έβαλαν κάτω».'), source)


def test_related_but_distinct_lemmas_are_not_the_learners_word():
    v = Vocabulary([VocabEntry('κατοικώ', 'due', 'to live in'), VocabEntry('δημοτικός', 'due')])
    assert v.lookup('κατοικώ').state == 'due'
    assert v.lookup('κατοικούν').state == 'due'
    for related in ('κατοικίδιο', 'δημοτικότητα', 'δημοτικιστής'):
        assert v.lookup(related).state == NEW, related
        assert v.lookup(related).entry is None, related
    targets = select_targets(v, 'Το κατοικίδιο κοιμάται.')
    assert not any(t.in_article for t in targets)
    assert targets_used(v, 'Το κατοικίδιο κοιμάται.', targets) == []
    assert [t for _, t in v.annotate('Το κατοικίδιο κοιμάται.') if t.entry] == []


def test_inflected_forms_after_an_aspect_marker_still_match():
    v = Vocabulary([VocabEntry('δυσκολεύομαι', 'lesson')])
    for form in ('δυσκολεύτηκε', 'δυσκολεύτηκαν', 'δυσκολευτούμε', 'δυσκολεύομαι'):
        assert v.lookup(form).lemma == 'δυσκολεύομαι', form


def test_a_dictionary_lemma_is_not_overridden_by_a_prefix_match():
    class Dict:
        def candidates(self, word):
            return ['κατοικίδιο'] if word == 'κατοικιδίου' else []

    v = Vocabulary([VocabEntry('κατοικώ', 'due')], lemmatizer=Dict())
    assert v.lookup('κατοικιδίου').state == NEW
    assert v.lookup('κατοικιδίου').lemma == 'κατοικίδιο'


def test_a_dictionary_proper_name_opening_a_sentence_is_still_checked(article, adapted):
    records = [json.loads(line) for line in KAIKKI.read_text(encoding='utf-8').splitlines() if line.strip()]
    records.append({'word': 'Μανωλάκης', 'lang_code': 'el', 'pos': 'name',
                    'senses': [{'glosses': ['a male surname']}]})
    v = Vocabulary.from_file(VOCAB, lemmatizer=KaikkiDictionary(records))
    targets = select_targets(v, article.text)
    report = check_adaptation(adapted.replace('Φέτος η σοδειά', 'Μανωλάκης, η σοδειά'),
                              article.text, targets, v)
    assert [r.name for r in report.results if not r.passed] == ['names'], report.failures()
    # An ordinary word the dictionary knows still opens a sentence freely.
    assert check_adaptation('Λαούτο έπαιξαν.', 'Έπαιξαν λαούτο.', [], v).get('names').passed


def test_a_lemmatizer_that_cannot_tell_names_does_not_exempt_them():
    class Dict:
        def candidates(self, word):
            return ['Μανωλάκης'] if fold(word) == fold('Μανωλάκης') else []

    v = Vocabulary(lemmatizer=Dict())
    assert not check_adaptation('Μανωλάκης ήρθε.', 'Ήρθε κάποιος.', [], v).get('names').passed


def test_the_dictionary_lemma_wins_over_a_shared_stem():
    dictionary = KaikkiDictionary([{'word': 'κατοικία', 'lang_code': 'el', 'pos': 'noun',
                                    'senses': [{'glosses': ['residence']}]}])
    v = Vocabulary([VocabEntry('κατοικώ', 'due', 'to live in')], lemmatizer=dictionary)
    info = v.lookup('κατοικία')
    assert (info.lemma, info.state, info.entry) == ('κατοικία', NEW, None)
    targets = select_targets(v, 'Η κατοικία είναι παλιά.')
    assert not any(t.in_article for t in targets)
    assert targets_used(v, 'Η κατοικία είναι παλιά.', targets) == []
    assert v.lookup('κατοικούν').state == 'due'  # a form the dictionary does not know


def test_ambiguous_ordinals_warn_without_failing(vocabulary):
    report = check_adaptation('Ήρθε για πρώτη φορά.', 'Ήρθε ξανά.', [], vocabulary)
    numbers = report.get('numbers')
    assert numbers.passed
    assert 'πρώτη' in numbers.warning
    assert report.warnings() == [f'numbers: {numbers.warning}']
    assert report.to_dict()['warnings'] == report.warnings()
    assert check_adaptation('Ήρθε για πρώτη φορά.', 'Πρώτη φορά.', [], vocabulary).get('numbers').warning is None
    # εκτός ("except") folds like έκτος ("sixth") but is not a number.
    assert check_adaptation('Όλοι εκτός από τον Νίκο.', 'Όλοι.', [], vocabulary).get('numbers').passed


# Function phrases and sense choice (greek-utils#18)

ISSUE_18_RECORDS = [
    {'word': 'σύμφωνο', 'lang_code': 'el', 'pos': 'noun', 'senses': [{'glosses': ['consonant']}],
     'forms': [{'form': 'σύμφωνα', 'tags': ['nominative', 'plural']}]},
    {'word': 'ανάρτηση', 'lang_code': 'el', 'pos': 'noun', 'senses': [
        {'glosses': ['hanging, suspending (of a picture, etc)'], 'tags': ['feminine']},
        {'glosses': ['suspension (of machinery, motor vehicles, etc)'], 'tags': ['feminine'],
         'topics': ['automotive', 'transport', 'vehicles']},
        {'glosses': ['post (display message)'], 'tags': ['feminine', 'figuratively']},
    ], 'forms': [{'form': 'ανάρτησή', 'tags': ['nominative', 'singular']}]},
    {'word': 'λύρα', 'lang_code': 'el', 'pos': 'noun', 'senses': [
        {'glosses': ['pound (old currency)'], 'tags': ['historical']},
        {'glosses': ['lyre']},
    ]},
]


@pytest.fixture
def issue_18_vocabulary():
    dictionary = KaikkiDictionary(ISSUE_18_RECORDS)
    vocabulary = Vocabulary(
        [VocabEntry('σύμφωνο', 'due', 'consonant'), VocabEntry('ανακοίνωση', 'due', 'announcement')],
        lemmatizer=dictionary,
    )
    return vocabulary, dictionary


def test_symfona_me_is_a_function_phrase(issue_18_vocabulary):
    vocabulary, _ = issue_18_vocabulary
    text = 'Σύμφωνα με την ανακοίνωση, η κυβέρνηση θα αποφασίσει. Τα σύμφωνα της λέξης είναι δύο.'
    states = [(t.text, info.state) for t, info in vocabulary.annotate(text)]
    assert states[:2] == [('Σύμφωνα', FUNCTION), ('με', FUNCTION)]
    # Outside the phrase it is still the plural of σύμφωνο, the deck word.
    assert ('σύμφωνα', 'due') in states
    # A comma between the words breaks the phrase.
    broken = vocabulary.annotate('Μίλησε για τα σύμφωνα, με χαρά.')
    assert [info.state for t, info in broken if t.text == 'σύμφωνα'] == ['due']


def test_symfona_me_is_never_a_target(issue_18_vocabulary):
    vocabulary, _ = issue_18_vocabulary
    text = 'Σύμφωνα με τον υπουργό, το έργο θα ολοκληρωθεί σύντομα.'
    targets = select_targets(vocabulary, text, quotas=(('due', 5),))
    assert {t.lemma: t.in_article for t in targets}['σύμφωνο'] is False


def test_single_word_prepositions_are_function_words(issue_18_vocabulary):
    vocabulary, _ = issue_18_vocabulary
    annotated = vocabulary.annotate('Λόγω της κακοκαιρίας, τα σχολεία έκλεισαν μέσω απόφασης εξαιτίας του ανέμου.')
    assert {t.text: info.state for t, info in annotated if t.folded in {'λογω', 'μεσω', 'εξαιτιασ'}} == {
        'Λόγω': FUNCTION, 'μέσω': FUNCTION, 'εξαιτίας': FUNCTION}


def test_gloss_prefers_the_sense_the_context_points_to(issue_18_vocabulary):
    vocabulary, dictionary = issue_18_vocabulary
    social = 'Σε ανάρτησή του στο Facebook ο δήμαρχος έγραψε ότι το έργο τελείωσε.'
    gloss = GlossResolver(vocabulary, dictionary).resolve('ανάρτηση', social, online=False)
    assert gloss.text.startswith('post (display message)')
    speech = 'Σε ανάρτησή του ο υπουργός ανέφερε ότι η συμφωνία είναι κοντά.'
    gloss = GlossResolver(vocabulary, dictionary).resolve('ανάρτηση', speech, online=False)
    assert gloss.text.startswith('post (display message)')
    # Without a cue, Wiktionary's order stands.
    plain = 'Η ανάρτηση του πίνακα στον τοίχο πήρε ώρα.'
    gloss = GlossResolver(vocabulary, dictionary).resolve('ανάρτηση', plain, online=False)
    assert gloss.text.startswith('hanging, suspending')


def test_gloss_puts_historical_senses_last(issue_18_vocabulary):
    vocabulary, dictionary = issue_18_vocabulary
    gloss = GlossResolver(vocabulary, dictionary).resolve('λύρα', online=False)
    assert gloss.text == 'lyre; pound (old currency)'


def test_build_glosses_anartisi_as_post_and_skips_symfona(issue_18_vocabulary):
    vocabulary, dictionary = issue_18_vocabulary
    text = ('Σύμφωνα με την ανακοίνωση, ο δήμαρχος μίλησε. '
            'Σε ανάρτησή του στο Facebook έγραψε ότι το έργο τελείωσε.')
    result = build(parse_text(text), vocabulary, GlossResolver(vocabulary, dictionary),
                   supplied_text=text)
    tokens = {t['text']: t for t in result['tokens']}
    assert tokens['Σύμφωνα']['state'] == FUNCTION and not tokens['Σύμφωνα']['target']
    assert 'σύμφωνο' not in result['glosses']
    assert result['glosses']['ανάρτηση']['text'].startswith('post (display message)')
