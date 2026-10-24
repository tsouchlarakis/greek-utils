"""Choose the day's target words from the learner's vocabulary states."""

from dataclasses import asdict, dataclass

from greek_utils.reader.text import fold
from greek_utils.reader.vocab import Vocabulary

# Per-state quotas, in priority order: due cards first (reading them sends the learner
# back to their review queue), then recently learned words, then lesson words.
DEFAULT_QUOTAS = (('due', 6), ('recent', 4), ('lesson', 5))


@dataclass(frozen=True)
class Target:
    lemma: str
    state: str
    in_article: bool
    gloss: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def article_lemmas(vocabulary: Vocabulary, text: str) -> set[str]:
    """Folded lemmas of the learner's entries that occur, in any form, in the text."""
    return {fold(info.lemma) for _, info in vocabulary.annotate(text) if info.entry is not None}


def select_targets(
    vocabulary: Vocabulary,
    article_text: str,
    quotas: tuple[tuple[str, int], ...] = DEFAULT_QUOTAS,
) -> list[Target]:
    """
    Up to the quota of each state, keeping the caller's order within a state (put the
    most overdue or most recent first) but preferring words already in the article,
    which the adaptation can then keep naturally.
    """
    present = article_lemmas(vocabulary, article_text)
    chosen: list[Target] = []
    seen: set[str] = set()
    for state, quota in quotas:
        pool = [e for e in vocabulary.entries if e.state == state and fold(e.lemma) not in seen]
        pool.sort(key=lambda e: fold(e.lemma) not in present)  # stable: keeps caller order
        for entry in pool[:quota]:
            seen.add(fold(entry.lemma))
            chosen.append(Target(entry.lemma, state, fold(entry.lemma) in present, entry.gloss))
    return chosen


def targets_used(vocabulary: Vocabulary, text: str, targets: list[Target]) -> list[str]:
    """The target lemmas that appear, in any form, in the text."""
    present = article_lemmas(vocabulary, text)
    return [t.lemma for t in targets if fold(t.lemma) in present]
