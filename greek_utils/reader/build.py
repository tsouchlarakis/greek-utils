"""Turn an article into a checked reading text with targets and glosses."""

from greek_utils.reader.adapt import DEFAULT_RULES, Adapter, Rules, adapt, build_prompt, check_supplied
from greek_utils.reader.article import Article
from greek_utils.reader.gloss import GlossResolver
from greek_utils.reader.targets import select_targets
from greek_utils.reader.text import fold, sentences
from greek_utils.reader.vocab import NEW, Vocabulary


def build(
    article: Article,
    vocabulary: Vocabulary,
    resolver: GlossResolver | None = None,
    adapter: Adapter | None = None,
    supplied_text: str | None = None,
    rules: Rules = DEFAULT_RULES,
) -> dict:
    """
    Select targets, adapt (through ``adapter``, or check ``supplied_text``, or fall back
    to an excerpt), then annotate and gloss the resulting text. Glosbe and other online
    sources are consulted only for new and target words; every other word gets an
    offline gloss when one exists.
    """
    targets = select_targets(vocabulary, article.text)
    if supplied_text is not None:
        adaptation = check_supplied(supplied_text, article, targets, vocabulary, rules)
    else:
        adaptation = adapt(article, targets, vocabulary, adapter, rules)

    target_keys = {fold(t.lemma) for t in targets}
    text_sentences = sentences(adaptation.text)
    tokens = []
    glosses = {}
    for tok, info in vocabulary.annotate(adaptation.text):
        is_target = info.is_vocab and fold(info.lemma) in target_keys
        tokens.append({
            'text': tok.text,
            'start': tok.start,
            'end': tok.end,
            'lemma': info.lemma,
            'state': info.state,
            'target': is_target,
        })
        if resolver is None or not info.is_vocab or info.lemma in glosses:
            continue
        context = text_sentences[tok.sentence] if tok.sentence < len(text_sentences) else ''
        gloss = resolver.resolve(info.lemma, context, online=is_target or info.state == NEW)
        glosses[info.lemma] = gloss.to_dict() if gloss else None

    return {
        'source': {k: v for k, v in article.to_dict().items() if k != 'text'},
        'article_text': article.text,
        'targets': [t.to_dict() for t in targets],
        'prompt': build_prompt(article, targets, rules),
        'adaptation': adaptation.to_dict(),
        'tokens': tokens,
        'glosses': glosses,
    }
