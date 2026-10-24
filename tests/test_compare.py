"""
Read-aloud comparison. The reference text and transcripts are synthetic.

Every scenario except the clean baseline is built so that a naive positional comparison
(zip the text and transcript words, compare pairwise, measure the gap before each heard
word) gets it wrong; ``test_naive_comparer_fails_every_scenario`` keeps that true.
"""

import json
import unicodedata
from dataclasses import dataclass, field

import pytest
from click.testing import CliRunner

from greek_utils.cli import cli
from greek_utils.reader.compare import (
    CLEAN,
    MISREAD,
    SKIPPED,
    STRESS,
    UNCLEAR,
    HeardWord,
    compare,
    parse_transcript,
)
from greek_utils.reader.text import fold, tokenize

REF = (
    'Κάθε πρωί η γιαγιά ποτίζει τα λουλούδια στην αυλή. Πότε θα έρθεις στο χωριό; '
    'Ο αντιδήμαρχος μάς περιμένει στις 6 το απόγευμα.'
)
REF_WORDS = [t.text for t in tokenize(REF)]
# 0 Κάθε 1 πρωί 2 η 3 γιαγιά 4 ποτίζει 5 τα 6 λουλούδια 7 στην 8 αυλή 9 Πότε 10 θα
# 11 έρθεις 12 στο 13 χωριό 14 Ο 15 αντιδήμαρχος 16 μάς 17 περιμένει 18 στις 19 6
# 20 το 21 απόγευμα

WORD_SECONDS = 0.4
GAP_SECONDS = 0.1


def timed(words: list[str], gaps: dict[int, float] | None = None,
          confidence: dict[int, float] | None = None) -> list[HeardWord]:
    """Heard words with steady timing; ``gaps[k]`` is the silence before heard word k."""
    gaps = gaps or {}
    confidence = confidence or {}
    heard, t = [], 0.0
    for k, w in enumerate(words):
        if k:
            t += gaps.get(k, GAP_SECONDS)
        heard.append(HeardWord(w, round(t, 3), round(t + WORD_SECONDS, 3), confidence.get(k, 0.95)))
        t += WORD_SECONDS
    return heard


def without(*indexes: int) -> list[str]:
    return [w for i, w in enumerate(REF_WORDS) if i not in indexes]


def replaced(changes: dict[int, list[str]], words: list[str] | None = None) -> list[str]:
    words = words if words is not None else REF_WORDS
    out = []
    for i, w in enumerate(words):
        out.extend(changes.get(i, [w]))
    return out


@dataclass
class Scenario:
    name: str
    heard: list[HeardWord]
    statuses: dict[int, str] = field(default_factory=dict)  # every other word is clean
    paused: set[int] = field(default_factory=set)
    repeats: int = 0
    extras: int = 0
    heard_as: dict[int, str] = field(default_factory=dict)

    def signature(self) -> tuple:
        return (
            tuple(self.statuses.get(i, CLEAN) for i in range(len(REF_WORDS))),
            tuple(sorted(self.paused)),
            self.repeats,
            self.extras,
        )


SCENARIOS = [
    Scenario(
        'baseline: case, punctuation and missing accents are clean',
        timed(['ΚΑΘΕ', 'ΠΡΩΙ'] + [w.lower() for w in REF_WORDS[2:16]] + ['μας'] + REF_WORDS[17:]),
    ),
    Scenario(
        'one skipped word does not shift the rest',
        timed(without(3)),
        statuses={3: SKIPPED},
    ),
    Scenario(
        'a skipped run of three words',
        timed(without(7, 8, 9)),
        statuses={7: SKIPPED, 8: SKIPPED, 9: SKIPPED},
    ),
    Scenario(
        'a restart then a misread',
        timed(replaced({5: ['τα', 'τα'], 6: ['λουκούμια']})),
        statuses={6: MISREAD},
        repeats=1,
        heard_as={6: 'λουκούμια'},
    ),
    Scenario(
        'a stress pair after a skip',
        timed(replaced({3: [], 9: ['ποτέ']})),
        statuses={3: SKIPPED, 9: STRESS},
        heard_as={9: 'ποτέ'},
    ),
    Scenario(
        'a word heard as two pieces, and a skip',
        timed(replaced({1: [], 15: ['αντι', 'δήμαρχος']})),
        statuses={1: SKIPPED},
    ),
    Scenario(
        'a number spoken as words is unclear, not an error',
        timed(replaced({2: [], 19: ['έξι']})),
        statuses={2: SKIPPED, 19: UNCLEAR},
    ),
    Scenario(
        'a low-confidence mismatch is unclear, not misread',
        timed(without(0)[:5] + ['λουκούμια'] + without(0)[6:], confidence={5: 0.3}),
        statuses={0: SKIPPED, 6: UNCLEAR},
    ),
    Scenario(
        'a long pause after a skip lands on the right word',
        # γιαγιά (3) skipped; 2.0 s before αντιδήμαρχος, 1.0 s before χωριό (below 1.5).
        timed(without(3), gaps={14: 2.0, 12: 1.0}),
        statuses={3: SKIPPED},
        paused={15},
    ),
    Scenario(
        'silence around a filler adds up to a pause',
        # 0.9 s, a filler, 0.9 s: each gap is short, the hesitation is 1.8 s.
        timed(replaced({9: ['εεε', 'Πότε']}), gaps={9: 0.9, 10: 0.9}),
        paused={9},
        extras=1,
    ),
]

def actual_signature(result) -> tuple:
    return (
        tuple(w.status for w in result.words),
        tuple(w.index for w in result.words if w.paused),
        result.counts['repeats'],
        result.counts['extras'],
    )


@pytest.mark.parametrize('scenario', SCENARIOS, ids=lambda s: s.name)
def test_scenarios(scenario):
    result = compare(REF, scenario.heard)
    assert [w.text for w in result.words] == REF_WORDS
    assert actual_signature(result) == scenario.signature()
    for i, heard in scenario.heard_as.items():
        assert result.words[i].heard == heard


def naive_compare(text: str, heard: list[HeardWord], pause_seconds: float = 1.5) -> tuple:
    """Positional comparison: what the alignment exists to beat."""
    ref = tokenize(text)
    statuses, paused = [], []
    for i, t in enumerate(ref):
        if i >= len(heard):
            statuses.append(SKIPPED)
            continue
        statuses.append(CLEAN if t.folded == fold(heard[i].text) else MISREAD)
        if i and heard[i].start - heard[i - 1].end >= pause_seconds:
            paused.append(i)
    extras = max(0, len(heard) - len(ref))
    return tuple(statuses), tuple(paused), 0, extras


@pytest.mark.parametrize('scenario', SCENARIOS[1:], ids=lambda s: s.name)
def test_naive_comparer_fails_every_scenario(scenario):
    assert naive_compare(REF, scenario.heard) != scenario.signature()


def test_naive_comparer_passes_baseline():
    assert naive_compare(REF, SCENARIOS[0].heard) == SCENARIOS[0].signature()


def test_join_two_text_words_heard_as_one():
    result = compare("Πήγε σ' αυτό το σπίτι.", 'πήγε σαυτό το σπίτι')
    assert [w.status for w in result.words] == [CLEAN] * 5
    assert result.words[1].heard == result.words[2].heard == 'σαυτό'
    assert not result.extras


def test_stress_needs_an_accent_on_both_sides():
    assert compare('Πότε έρχεσαι;', 'ποτε έρχεσαι').words[0].status == CLEAN
    assert compare('Πότε έρχεσαι;', 'ΠΟΤΕ έρχεσαι').words[0].status == CLEAN
    assert compare('Πότε έρχεσαι;', 'ποτέ έρχεσαι').words[0].status == STRESS
    assert compare('Ο νόμος άλλαξε.', 'ο νομός άλλαξε').words[1].status == STRESS


def test_pause_values_and_threshold():
    heard = timed(without(3), gaps={14: 2.0, 12: 1.0})
    result = compare(REF, heard)
    assert result.words[15].pause_before == pytest.approx(2.0)
    assert result.words[13].pause_before == pytest.approx(1.0)
    assert result.words[0].pause_before is None  # leading silence is not hesitation
    assert result.words[3].pause_before is None  # skipped
    assert compare(REF, heard, pause_seconds=0.9).counts['paused'] == 2


def test_reading_speed():
    heard = timed(REF_WORDS)
    result = compare(REF, heard, native_seconds=8.8)
    seconds = len(REF_WORDS) * WORD_SECONDS + (len(REF_WORDS) - 1) * GAP_SECONDS
    assert result.reading_seconds == pytest.approx(seconds)
    assert result.wpm == pytest.approx(round(len(REF_WORDS) / seconds * 60, 1))
    assert result.native_wpm == pytest.approx(150.0)
    assert result.relative_speed == pytest.approx(round(result.wpm / 150.0, 2))


def test_plain_text_transcript_has_no_timing():
    result = compare(REF, ' '.join(without(3)))
    assert result.words[3].status == SKIPPED
    assert result.wpm is None and result.reading_seconds is None
    assert not any(w.paused for w in result.words)


def test_headline_and_stumbles():
    result = compare(REF, timed(replaced({3: [], 5: ['τα', 'τα'], 6: ['λουκούμια']}), gaps={15: 2.0}))
    stumbles = [(w.index, w.status, w.paused) for w in result.stumbles()]
    assert stumbles == [(3, SKIPPED, False), (6, MISREAD, False), (15, CLEAN, True)]
    assert result.headline == f'{len(REF_WORDS) - 3} of {len(REF_WORDS)} words read cleanly'


WHISPER_RESULT = {
    'text': ' Κάθε πρωί η γιαγιά ποτίζει.',
    'segments': [{
        'text': ' Κάθε πρωί η γιαγιά ποτίζει.',
        'words': [
            {'word': ' Κάθε', 'start': 0.0, 'end': 0.3, 'probability': 0.99},
            {'word': ' πρωί', 'start': 0.4, 'end': 0.7, 'probability': 0.98},
            {'word': ' η', 'start': 0.8, 'end': 0.9, 'probability': 0.97},
            {'word': ' γιαγιά', 'start': 1.0, 'end': 1.4, 'probability': 0.95},
            {'word': ' ποτίζει.', 'start': 3.5, 'end': 4.0, 'probability': 0.4},
        ],
    }],
}


def test_parse_whisper_segments():
    heard = parse_transcript(WHISPER_RESULT)
    assert [h.text for h in heard] == ['Κάθε', 'πρωί', 'η', 'γιαγιά', 'ποτίζει']
    assert heard[4] == HeardWord('ποτίζει', 3.5, 4.0, 0.4)
    result = compare('Κάθε πρωί η γιαγιά ποτίζει.', WHISPER_RESULT)
    assert result.words[4].status == CLEAN  # a low-confidence match is still a match
    assert result.words[4].paused and result.words[4].pause_before == pytest.approx(2.1)


def test_parse_plain_word_list_and_text():
    assert [h.text for h in parse_transcript([{'text': 'καλή', 'start': 0, 'end': 1}, 'μέρα'])] == ['καλή', 'μέρα']
    assert [h.text for h in parse_transcript({'text': 'Καλή μέρα!'})] == ['Καλή', 'μέρα']


def test_cli_compare(tmp_path):
    text = tmp_path / 'text.txt'
    text.write_text(REF, encoding='utf-8')
    transcript = tmp_path / 'heard.json'
    heard = timed(replaced({3: [], 9: ['ποτέ']}), gaps={14: 2.0})
    transcript.write_text(json.dumps([
        {'word': h.text, 'start': h.start, 'end': h.end, 'probability': h.confidence} for h in heard
    ], ensure_ascii=False), encoding='utf-8')

    out = CliRunner().invoke(cli, ['reader', 'compare', str(text), str(transcript)])
    assert out.exit_code == 0, out.output
    assert f'{len(REF_WORDS) - 3} of {len(REF_WORDS)} words read cleanly' in out.output
    assert 'γιαγιά: skipped' in out.output
    assert 'Πότε: stress, heard «ποτέ»' in out.output
    assert 'αντιδήμαρχος: paused 2.0s' in out.output

    out = CliRunner().invoke(cli, ['reader', 'compare', str(text), str(transcript), '--json'])
    data = json.loads(out.output)
    assert data['counts']['skipped'] == 1 and data['counts']['stress'] == 1 and data['counts']['paused'] == 1


# Review fixes (PR #13)


def nfd(text: str) -> str:
    return unicodedata.normalize('NFD', text)


def test_decomposed_accents_stay_inside_their_word():
    assert [t.text for t in tokenize(nfd('Καλημέρα κόσμε.'))] == [nfd('Καλημέρα'), nfd('κόσμε')]
    for reference, transcript in [(nfd('Καλημέρα κόσμε.'), 'Καλημέρα κόσμε.'),
                                  ('Καλημέρα κόσμε.', nfd('Καλημέρα κόσμε.')),
                                  (nfd('Καλημέρα κόσμε.'), nfd('Καλημέρα κόσμε.'))]:
        result = compare(reference, transcript)
        assert [w.status for w in result.words] == [CLEAN, CLEAN]
    assert compare('Πότε', nfd('ποτέ')).words[0].status == STRESS
    assert compare(nfd('Πότε'), 'ποτέ').words[0].status == STRESS
    assert compare(nfd('Πότε'), nfd('ποτέ')).words[0].status == STRESS
    assert compare(nfd('Πότε'), nfd('πότε')).words[0].status == CLEAN


def test_apostrophe_is_not_a_letter_when_comparing_accents():
    # σ'αυτό and σαυτό are the same letters with the accent on the same syllable.
    assert compare("Πήγε σ'αυτό το σπίτι.", 'πήγε σαυτό το σπίτι').words[1].status == CLEAN


@pytest.mark.parametrize('reference, heard, statuses', [
    # split: the accent moved from δή to αντί
    ('αντιδήμαρχος', 'αντί δημαρχος', [STRESS]),
    # join: the accent moved from αυτό to σά
    ("σ' αυτό", 'σάυτο', [CLEAN, STRESS]),
    # the accent where it belongs, or no accent to judge, stays clean
    ('αντιδήμαρχος', 'αντι δήμαρχος', [CLEAN]),
    ('αντιδήμαρχος', 'αντί δήμαρχος', [CLEAN]),
    ('αντιδήμαρχος', 'αντι δημαρχος', [CLEAN]),
    ("σ' αυτό", 'σαυτό', [CLEAN, CLEAN]),
    ("σ' αυτό", 'σαυτο', [CLEAN, CLEAN]),
    # join: each text word is judged on its own accent, not the span's
    ('καλημέρα κόσμε', 'καλημέρακοσμέ', [CLEAN, STRESS]),
    ('καλημέρα κόσμε', 'καλήμερακόσμε', [STRESS, CLEAN]),
    ('καλημέρα κόσμε', 'καλημέρακόσμε', [CLEAN, CLEAN]),
    ('καλημέρα κόσμε', 'καλημερακοσμέ', [CLEAN, STRESS]),  # one accent heard, on κόσμε
    # an accent heard on an unaccented clitic belongs to the accented word beside it
    ('το σπίτι', 'τόσπιτι', [CLEAN, STRESS]),
])
def test_split_and_join_are_checked_for_stress(reference, heard, statuses):
    result = compare(reference, heard)
    assert [w.status for w in result.words] == statuses
    assert not result.extras


def test_split_stress_with_low_confidence_is_unclear():
    heard = [HeardWord('αντί', 0.0, 0.4, 0.3), HeardWord('δημαρχος', 0.5, 1.0, 0.9)]
    assert compare('αντιδήμαρχος', heard).words[0].status == UNCLEAR


def test_join_stress_with_low_confidence_is_unclear_only_where_it_moved():
    heard = [HeardWord('καλημέρακοσμέ', 0.0, 1.0, 0.3)]
    assert [w.status for w in compare('καλημέρα κόσμε', heard).words] == [CLEAN, UNCLEAR]


def test_silence_inside_a_split_word_is_a_pause():
    heard = [HeardWord('ο', 0.0, 0.2), HeardWord('αντι', 0.3, 0.6),
             HeardWord('δήμαρχος', 2.7, 3.2), HeardWord('ήρθε', 3.3, 3.7)]
    result = compare('Ο αντιδήμαρχος ήρθε.', heard)
    assert [w.status for w in result.words] == [CLEAN, CLEAN, CLEAN]
    assert result.words[1].pause_before == pytest.approx(2.2)  # 0.1 before, 2.1 inside
    assert result.words[1].paused
    assert result.words[2].pause_before == pytest.approx(0.1)  # not counted twice
    assert result.counts['paused'] == 1


def test_silence_inside_a_number_read_as_words_is_a_pause():
    heard = [HeardWord('στις', 0.0, 0.3), HeardWord('δεκα', 0.4, 0.8), HeardWord('πέντε', 3.0, 3.4)]
    result = compare('στις 15', heard)
    assert result.words[1].status == UNCLEAR
    assert result.words[1].paused


def test_short_silence_inside_a_split_word_is_not_a_pause():
    heard = [HeardWord('αντι', 0.0, 0.3), HeardWord('δήμαρχος', 0.6, 1.1)]
    assert not compare('αντιδήμαρχος', heard).words[0].paused
