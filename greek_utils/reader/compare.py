"""
Compare a read-aloud transcript with the text that was read.

The transcript (plain text, or words with timings and confidence as speech recognizers
such as Whisper return them) is aligned to the text word by word with a weighted edit
distance, so one skipped or repeated word does not shift every word after it. Each text
word then gets a status:

=========  ==========================================================================
clean      the same word (case, punctuation and missing accents ignored)
misread    a different word was heard
stress     the same letters with the accent on a different syllable (πότε / ποτέ)
skipped    nothing in the transcript lines up with it
unclear    a mismatch the recognizer itself was unsure of (confidence below the
           threshold), or a number spoken as words; never counted as an error
=========  ==========================================================================

Words also carry ``pause_before``: the silence, in seconds, between the previous text
word and this one (restarts and fillers in between excluded; silence inside a word heard
as several pieces included), and ``paused`` when that reaches the threshold. Heard words that line up with no text word are ``extras``,
labeled ``repeat`` when they repeat a nearby text word (a restart).

This is not pronunciation scoring. A recognizer tends to recover the intended word, so
a near-miss pronunciation usually comes back as the right word.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from greek_utils.reader.text import (
    Token,
    accent_position,
    accent_positions,
    fold,
    is_number_word,
    levenshtein,
    strict,
    tokenize,
)

CLEAN = 'clean'
MISREAD = 'misread'
STRESS = 'stress'
SKIPPED = 'skipped'
UNCLEAR = 'unclear'
ERRORS = (MISREAD, STRESS, SKIPPED)

DEFAULT_PAUSE_SECONDS = 1.5
DEFAULT_MIN_CONFIDENCE = 0.5

SKIP_COST = 1.0
EXTRA_COST = 1.0
STRESS_COST = 0.05
MERGE_COST = 0.1
NUMBER_COST = 0.1
MISREAD_BASE = 0.6  # + normalized letter distance, so a misread costs 0.6-1.6 < skip + extra
MAX_NUMBER_WORDS = 6
REPEAT_WINDOW = 2

@dataclass(frozen=True)
class HeardWord:
    text: str
    start: float | None = None
    end: float | None = None
    confidence: float | None = None


def parse_transcript(data) -> list[HeardWord]:
    """
    Accepts plain text, a list of words (``word``/``text``, ``start``, ``end``,
    ``probability``/``confidence``), or a recognizer result with ``words`` or
    ``segments[].words``. Punctuation is dropped; a heard item holding several words
    gives each of them its timing.
    """
    if isinstance(data, str):
        return [HeardWord(t.text) for t in tokenize(data)]
    if isinstance(data, dict):
        if data.get('words'):
            return parse_transcript(data['words'])
        segments = data.get('segments') or []
        seg_words = [w for s in segments for w in s.get('words') or []]
        if seg_words:
            return parse_transcript(seg_words)
        if segments:
            return parse_transcript(' '.join(s.get('text', '') for s in segments))
        return parse_transcript(data.get('text', ''))
    heard = []
    for item in data:
        if isinstance(item, str):
            heard.extend(HeardWord(t.text) for t in tokenize(item))
            continue
        text = item.get('word', item.get('text', ''))
        conf = item.get('probability', item.get('confidence', item.get('score')))
        for t in tokenize(text):
            heard.append(HeardWord(t.text, item.get('start'), item.get('end'), conf))
    return heard


def load_transcript(path: str | Path) -> list[HeardWord]:
    content = Path(path).read_text(encoding='utf-8')
    if str(path).lower().endswith('.json'):
        return parse_transcript(json.loads(content))
    return parse_transcript(content)


@dataclass
class WordResult:
    index: int
    text: str
    status: str
    heard: str | None = None
    start: float | None = None
    end: float | None = None
    confidence: float | None = None
    pause_before: float | None = None
    paused: bool = False
    note: str | None = None


@dataclass
class Extra:
    text: str
    kind: str  # 'repeat' or 'extra'
    after_index: int  # index of the text word it follows, -1 before the first
    start: float | None = None
    end: float | None = None


@dataclass
class Comparison:
    words: list[WordResult]
    extras: list[Extra] = field(default_factory=list)
    reading_seconds: float | None = None
    wpm: float | None = None
    native_wpm: float | None = None

    @property
    def counts(self) -> dict[str, int]:
        counts = {s: 0 for s in (CLEAN, MISREAD, STRESS, SKIPPED, UNCLEAR)}
        for w in self.words:
            counts[w.status] += 1
        counts['paused'] = sum(w.paused for w in self.words)
        counts['repeats'] = sum(e.kind == 'repeat' for e in self.extras)
        counts['extras'] = sum(e.kind == 'extra' for e in self.extras)
        return counts

    def stumbles(self) -> list[WordResult]:
        """Words to show in feedback: errors and pauses, in text order."""
        return [w for w in self.words if w.status in ERRORS or w.paused]

    @property
    def headline(self) -> str:
        n = len(self.words)
        return f'{n - len(self.stumbles())} of {n} words read cleanly'

    @property
    def relative_speed(self) -> float | None:
        if self.wpm and self.native_wpm:
            return round(self.wpm / self.native_wpm, 2)
        return None

    def to_dict(self) -> dict:
        return {
            'headline': self.headline,
            'counts': self.counts,
            'reading_seconds': self.reading_seconds,
            'wpm': self.wpm,
            'native_wpm': self.native_wpm,
            'relative_speed': self.relative_speed,
            'words': [asdict(w) for w in self.words],
            'extras': [asdict(e) for e in self.extras],
        }


def _substitution_cost(ref: str, heard: str) -> float:
    if strict(ref) == strict(heard):
        return 0.0
    a, b = fold(ref), fold(heard)
    if a == b:
        return STRESS_COST
    return MISREAD_BASE + levenshtein(a, b) / max(len(a), len(b), 1)


def _align(ref: list[Token], heard: list[HeardWord]) -> list[tuple[str, int, int, int, int]]:
    """
    Minimum-cost alignment. Returns operations ``(op, i0, i1, j0, j1)`` covering text
    words ``ref[i0:i1]`` and heard words ``heard[j0:j1]``, in order.
    """
    n, m = len(ref), len(heard)
    inf = float('inf')
    cost = [[inf] * (m + 1) for _ in range(n + 1)]
    back: list[list[tuple | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    cost[0][0] = 0.0
    ref_fold = [t.folded for t in ref]
    heard_fold = [fold(h.text) for h in heard]

    for i in range(n + 1):
        for j in range(m + 1):
            if i == 0 and j == 0:
                continue
            # Candidates in tie-break order: a restart leaves the earlier attempt as the
            # extra, because 'match' is tried before 'extra'.
            options = []
            if i and j:
                options.append((cost[i - 1][j - 1] + _substitution_cost(ref[i - 1].text, heard[j - 1].text),
                                ('match', 1, 1)))
            if i and j >= 2 and heard_fold[j - 2] + heard_fold[j - 1] == ref_fold[i - 1]:
                options.append((cost[i - 1][j - 2] + MERGE_COST, ('split', 1, 2)))
            if i >= 2 and j and ref_fold[i - 2] + ref_fold[i - 1] == heard_fold[j - 1]:
                options.append((cost[i - 2][j - 1] + MERGE_COST, ('join', 2, 1)))
            if i and j and ref[i - 1].kind == 'number':
                for k in range(1, min(MAX_NUMBER_WORDS, j) + 1):
                    if not is_number_word(heard[j - k].text):
                        break
                    if k == 1 and heard_fold[j - 1].isdigit():
                        continue  # digits compare as an ordinary match
                    options.append((cost[i - 1][j - k] + NUMBER_COST * k, ('number', 1, k)))
            if i:
                options.append((cost[i - 1][j] + SKIP_COST, ('skip', 1, 0)))
            if j:
                options.append((cost[i][j - 1] + EXTRA_COST, ('extra', 0, 1)))
            best_cost, best_op = options[0]
            for c, op in options[1:]:
                if c < best_cost - 1e-9:
                    best_cost, best_op = c, op
            cost[i][j] = best_cost
            back[i][j] = best_op

    ops = []
    i, j = n, m
    while i or j:
        op, di, dj = back[i][j]
        ops.append((op, i - di, i, j - dj, j))
        i, j = i - di, j - dj
    ops.reverse()
    return ops


def _classify(ref: Token, heard: HeardWord, min_confidence: float) -> str:
    if strict(ref.text) == strict(heard.text):
        return CLEAN
    low_confidence = heard.confidence is not None and heard.confidence < min_confidence
    if ref.folded == fold(heard.text):
        ref_accent, heard_accent = accent_position(ref.text), accent_position(heard.text)
        # A missing accent (capitals, a recognizer that drops them) asserts nothing.
        if ref_accent is None or heard_accent is None or ref_accent == heard_accent:
            return CLEAN
        return UNCLEAR if low_confidence else STRESS
    return UNCLEAR if low_confidence else MISREAD


def _classify_span(refs: list[Token], span: list[HeardWord], min_confidence: float) -> str:
    """
    Status for text words heard divided differently (one word as two, two as one). The
    letters already agree; only the accent can differ, and it is judged on the words
    laid end to end, with the same rules as a single word: a missing accent asserts
    nothing, and a mismatch the recognizer was unsure of is unclear.
    """
    ref_accents = accent_positions([t.text for t in refs])
    heard_accents = accent_positions([h.text for h in span])
    if not ref_accents or not heard_accents or ref_accents <= heard_accents or heard_accents <= ref_accents:
        return CLEAN
    confs = [h.confidence for h in span if h.confidence is not None]
    return UNCLEAR if confs and min(confs) < min_confidence else STRESS


def compare(
    text: str,
    transcript,
    pause_seconds: float = DEFAULT_PAUSE_SECONDS,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    native_seconds: float | None = None,
) -> Comparison:
    """
    Align ``transcript`` (anything ``parse_transcript`` accepts, or a list of
    ``HeardWord``) to ``text`` and classify every text word.
    """
    ref = tokenize(text)
    if isinstance(transcript, list) and all(isinstance(h, HeardWord) for h in transcript):
        heard = transcript
    else:
        heard = parse_transcript(transcript)

    results: list[WordResult] = []
    extras: list[Extra] = []
    last_aligned_j = None  # index of the last heard word aligned to a text word

    def silence_within(j0: int, j1: int) -> float:
        """Silence between the words of heard[j0:j1], which share one text word."""
        return sum(max(0.0, heard[k].start - heard[k - 1].end) for k in range(j0 + 1, j1)
                   if heard[k].start is not None and heard[k - 1].end is not None)

    def silence_before(j0: int) -> float | None:
        """Silence between the previous aligned heard word and heard[j0], skipping
        the speech of any extras (restarts, fillers) in between."""
        if last_aligned_j is None:
            return None
        total = 0.0
        for k in range(last_aligned_j + 1, j0 + 1):
            prev_end, start = heard[k - 1].end, heard[k].start
            if prev_end is None or start is None:
                return None
            total += max(0.0, start - prev_end)
        return round(total, 3)

    for op, i0, i1, j0, j1 in _align(ref, heard):
        if op == 'extra':
            h = heard[j0]
            after = i0 - 1
            window = ref[max(0, after - REPEAT_WINDOW + 1): after + REPEAT_WINDOW + 1]
            kind = 'repeat' if any(t.folded == fold(h.text) for t in window) else 'extra'
            extras.append(Extra(h.text, kind, after, h.start, h.end))
            continue
        if op == 'skip':
            results.append(WordResult(i0, ref[i0].text, SKIPPED))
            continue

        span = heard[j0:j1]
        heard_text = ' '.join(h.text for h in span)
        start, end = span[0].start, span[-1].end
        confs = [h.confidence for h in span if h.confidence is not None]
        conf = min(confs) if confs else None
        pause = silence_before(j0)
        if op in ('split', 'number') and len(span) > 1:
            # One text word heard as several: hesitating inside it is hesitating on it.
            inside = silence_within(j0, j1)
            if inside:
                pause = round((pause or 0.0) + inside, 3)

        span_status = _classify_span(ref[i0:i1], span, min_confidence) if op in ('split', 'join') else None
        for i in range(i0, i1):
            if op == 'match':
                status, note = _classify(ref[i], span[0], min_confidence), None
            elif op == 'number':
                status, note = UNCLEAR, 'number read as words; not checked'
            elif span_status == CLEAN or not accent_positions([ref[i].text]):
                status, note = CLEAN, None  # split or join: the same letters, divided differently
            else:  # only the text word that carries the accent can be misstressed
                status, note = span_status, None
            results.append(WordResult(
                index=i,
                text=ref[i].text,
                status=status,
                heard=heard_text,
                start=start,
                end=end,
                confidence=conf,
                pause_before=pause if i == i0 else 0.0 if pause is not None else None,
                paused=i == i0 and pause is not None and pause >= pause_seconds,
                note=note,
            ))
        last_aligned_j = j1 - 1

    timed = [h for h in heard if h.start is not None and h.end is not None]
    reading_seconds = wpm = None
    if timed:
        reading_seconds = round(timed[-1].end - timed[0].start, 3)
        read = sum(w.status != SKIPPED for w in results)
        if reading_seconds > 0:
            wpm = round(read / reading_seconds * 60, 1)
    native_wpm = round(len(ref) / native_seconds * 60, 1) if native_seconds else None

    return Comparison(results, extras, reading_seconds, wpm, native_wpm)
