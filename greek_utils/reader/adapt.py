"""
Adapting an article to a B2 reading text, and the deterministic checks on the result.

The adaptation itself is a pluggable ``Adapter``: any callable that takes the prompt and
returns Greek text. This module never calls a model. Without an adapter, or when an
adaptation fails its checks twice, the fallback is the best excerpt of the article.
"""

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from greek_utils.reader.article import Article
from greek_utils.reader.targets import Target, targets_used
from greek_utils.reader.text import sentences, tokenize
from greek_utils.reader.vocab import NAME, NUMBER, Vocabulary, new_ratio, stem

Adapter = Callable[[str], str]

ORIGIN_ADAPTER = 'adapter'
ORIGIN_SUPPLIED = 'supplied'
ORIGIN_EXCERPT = 'excerpt'
ORIGIN_FALLBACK = 'excerpt-fallback'


@dataclass(frozen=True)
class Rules:
    level: str = 'B2'
    prompt_min_words: int = 140
    prompt_max_words: int = 160
    min_words: int = 130
    max_words: int = 170
    min_new_ratio: float = 0.06
    max_new_ratio: float = 0.14
    min_targets: int = 8
    # Level heuristics: B2 news adaptations keep sentences short.
    max_mean_sentence_words: float = 20.0
    max_sentence_words: int = 32


DEFAULT_RULES = Rules()


PROMPT_TEMPLATE = """\
Adapt the Greek news article below into a reading text for a learner of Modern Greek at CEFR {level}.

Rules:
- Write {prompt_min_words}-{prompt_max_words} words of natural standard Modern Greek, in short paragraphs.
- {level} grammar. Prefer shorter sentences (about {mean_words} words on average, never more than {max_sentence_words}); keep idioms.
- Keep every fact, number, date and name exactly as in the article. Invent nothing.
- Quotations stay word for word, or are dropped. Never paraphrase inside quotation marks.
- Use at least {min_targets} of these target words, in any grammatical form, only where they fit naturally:
{target_lines}
- Output only the adapted text: a title on the first line, a blank line, then the text. No notes, no translation.
{failures}
Article title: {title}

Article:
{text}
"""


def build_prompt(article: Article, targets: list[Target], rules: Rules = DEFAULT_RULES,
                 failures: list[str] | None = None) -> str:
    failure_block = ''
    if failures:
        failure_block = (
            '\nYour previous attempt failed these checks; fix them:\n'
            + '\n'.join(f'- {f}' for f in failures) + '\n'
        )
    return PROMPT_TEMPLATE.format(
        level=rules.level,
        prompt_min_words=rules.prompt_min_words,
        prompt_max_words=rules.prompt_max_words,
        mean_words=int(rules.max_mean_sentence_words),
        max_sentence_words=rules.max_sentence_words,
        min_targets=min(rules.min_targets, len(targets)),
        target_lines='\n'.join(f'  - {t.lemma}' for t in targets) or '  (none)',
        failures=failure_block,
        title=article.title,
        text=article.text,
    )


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str
    value: float | int | list | None = None


@dataclass
class CheckReport:
    results: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    def failures(self) -> list[str]:
        return [f'{r.name}: {r.detail}' for r in self.results if not r.passed]

    def get(self, name: str) -> CheckResult:
        return next(r for r in self.results if r.name == name)

    def to_dict(self) -> dict:
        return {'passed': self.passed, 'results': [asdict(r) for r in self.results]}


QUOTE_RE = re.compile(r'«([^»]+)»|“([^”]+)”|"([^"]+)"')
NUMBER_RE = re.compile(r'\d+(?:[.,]\d+)*')


def _normalize_quote(text: str) -> str:
    return re.sub(r'\s+', ' ', text.replace('’', "'")).strip(' .,;')


def _body(text: str) -> str:
    """The text without a leading title line, which is not counted toward length."""
    parts = text.strip().split('\n\n', 1)
    first = parts[0].strip()
    if len(parts) == 2 and '\n' not in first and not re.search(r'[.!;;…»]$', first):
        return parts[1]
    return text


def check_adaptation(text: str, source: str, targets: list[Target], vocabulary: Vocabulary,
                     rules: Rules = DEFAULT_RULES) -> CheckReport:
    body = _body(text)
    tokens = tokenize(body)
    annotated = vocabulary.annotate(body)
    results = []

    n_words = len(tokens)
    results.append(CheckResult(
        'length', rules.min_words <= n_words <= rules.max_words,
        f'{n_words} words (want {rules.min_words}-{rules.max_words})', n_words,
    ))

    ratio, new, total = new_ratio(annotated)
    results.append(CheckResult(
        'new_ratio', rules.min_new_ratio <= ratio <= rules.max_new_ratio,
        f'{len(new)} of {total} content lemmas new ({ratio:.0%}; want '
        f'{rules.min_new_ratio:.0%}-{rules.max_new_ratio:.0%})', round(ratio, 4),
    ))

    used = targets_used(vocabulary, body, targets)
    need = min(rules.min_targets, len(targets))
    results.append(CheckResult(
        'targets', len(used) >= need,
        f'{len(used)} of {len(targets)} target words used (want at least {need})', used,
    ))

    lengths = [len(tokenize(s)) for s in sentences(body)]
    lengths = [n for n in lengths if n]
    mean = sum(lengths) / len(lengths) if lengths else 0.0
    longest = max(lengths, default=0)
    results.append(CheckResult(
        'sentence_length',
        mean <= rules.max_mean_sentence_words and longest <= rules.max_sentence_words,
        f'mean {mean:.1f} words, longest {longest} (want mean <= '
        f'{rules.max_mean_sentence_words:g}, longest <= {rules.max_sentence_words})', round(mean, 1),
    ))

    source_numbers = set(NUMBER_RE.findall(source))
    bad_numbers = sorted({n for n in NUMBER_RE.findall(body) if n not in source_numbers})
    results.append(CheckResult(
        'numbers', not bad_numbers,
        'every number is in the source' if not bad_numbers
        else 'not in the source: ' + ', '.join(bad_numbers), bad_numbers,
    ))

    source_keys = {t.folded for t in tokenize(source)}
    source_stems = {stem(k) for k in source_keys}
    bad_names = []
    for tok, info in annotated:
        if info.state != NAME or tok.kind == NUMBER:
            continue
        if tok.folded in source_keys or stem(tok.text) in source_stems:
            continue
        # Greek names inflect (Πετρούνιας, Πετρούνια): accept a shared stem prefix.
        s = stem(tok.text)
        if len(s) >= 4 and any(k.startswith(s) or s.startswith(stem(k)) for k in source_keys
                               if len(stem(k)) >= 4):
            continue
        bad_names.append(tok.text)
    bad_names = sorted(set(bad_names))
    results.append(CheckResult(
        'names', not bad_names,
        'every proper name is in the source' if not bad_names
        else 'not in the source: ' + ', '.join(bad_names), bad_names,
    ))

    source_norm = _normalize_quote(source)
    bad_quotes = []
    for m in QUOTE_RE.finditer(body):
        quote = _normalize_quote(next(g for g in m.groups() if g))
        if quote and quote not in source_norm:
            bad_quotes.append(quote)
    results.append(CheckResult(
        'quotes', not bad_quotes,
        'every quotation is verbatim' if not bad_quotes
        else 'not verbatim: ' + ' | '.join(f'«{q}»' for q in bad_quotes), bad_quotes,
    ))

    return CheckReport(results)


def excerpt(article_text: str, rules: Rules = DEFAULT_RULES) -> str:
    """
    The opening sentences of the article, up to the maximum length, in paragraphs. The
    fallback text, so there is always something to read.
    """
    out_paragraphs = []
    count = 0
    for paragraph in [p for p in re.split(r'\n\s*\n', article_text) if p.strip()]:
        kept = []
        for sentence in sentences(paragraph):
            n = len(tokenize(sentence))
            if count + n > rules.max_words:
                break
            kept.append(sentence)
            count += n
        if kept:
            out_paragraphs.append(' '.join(kept))
        if count >= rules.prompt_min_words or len(kept) < len(sentences(paragraph)):
            break
    return '\n\n'.join(out_paragraphs)


@dataclass
class Adaptation:
    text: str
    origin: str
    report: CheckReport
    attempts: list[dict] = field(default_factory=list)  # each: prompt, text, failures

    def to_dict(self) -> dict:
        return {
            'text': self.text,
            'origin': self.origin,
            'checks': self.report.to_dict(),
            'attempts': self.attempts,
        }


def adapt(article: Article, targets: list[Target], vocabulary: Vocabulary,
          adapter: Adapter | None = None, rules: Rules = DEFAULT_RULES, max_attempts: int = 2) -> Adaptation:
    """
    Run the adapter, check its output, retry once with the failures listed, and fall back
    to an excerpt when every attempt fails. With no adapter, return the checked excerpt.
    """
    def check(text: str) -> CheckReport:
        return check_adaptation(text, article.text, targets, vocabulary, rules)

    if adapter is None:
        text = excerpt(article.text, rules)
        return Adaptation(text, ORIGIN_EXCERPT, check(text))

    attempts = []
    failures = None
    for _ in range(max_attempts):
        prompt = build_prompt(article, targets, rules, failures)
        text = adapter(prompt).strip()
        report = check(text)
        attempts.append({'text': text, 'failures': report.failures()})
        if report.passed:
            return Adaptation(text, ORIGIN_ADAPTER, report, attempts)
        failures = report.failures()

    text = excerpt(article.text, rules)
    return Adaptation(text, ORIGIN_FALLBACK, check(text), attempts)


def check_supplied(text: str, article: Article, targets: list[Target], vocabulary: Vocabulary,
                   rules: Rules = DEFAULT_RULES) -> Adaptation:
    """Check an adaptation made elsewhere (by hand, or by a separate model run)."""
    return Adaptation(text.strip(), ORIGIN_SUPPLIED,
                      check_adaptation(text, article.text, targets, vocabulary, rules))
