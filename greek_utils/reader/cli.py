import importlib
import json
import sys
from pathlib import Path

import click

from greek_utils.reader import article as article_mod
from greek_utils.reader.build import build as build_text
from greek_utils.reader.compare import (
    DEFAULT_MIN_CONFIDENCE,
    DEFAULT_PAUSE_SECONDS,
    load_transcript,
)
from greek_utils.reader.compare import (
    compare as compare_text,
)
from greek_utils.reader.gloss import GlossResolver, KaikkiDictionary
from greek_utils.reader.vocab import Vocabulary


def _load_adapter(spec: str):
    module_name, _, attr = spec.partition(':')
    if not attr:
        raise click.BadParameter('use module:callable', param_hint='--adapter')
    return getattr(importlib.import_module(module_name), attr)


def _glosbe(word: str) -> list[str]:
    from greek_utils.verb_flashcard import scrape_glosbe_translation
    return scrape_glosbe_translation(word)


@click.group()
def reader():
    """Daily graded reading: build a text from an article, compare a read-aloud."""


@reader.command()
@click.argument('source')
@click.option('--vocab', 'vocab_path', type=click.Path(exists=True, dir_okay=False), required=True,
              help='Vocabulary-state JSON ({"words": [{"lemma", "state", "gloss"}], "frequent": [...]}).')
@click.option('--frequent', 'frequent_path', type=click.Path(exists=True, dir_okay=False),
              help='Common lemmas that count as known, one per line.')
@click.option('--kaikki', 'kaikki_path', type=click.Path(exists=True, dir_okay=False),
              help='kaikki.org Greek Wiktionary extract (JSON lines) for lemmas and glosses.')
@click.option('--adapted', 'adapted_path', type=click.Path(exists=True, dir_okay=False),
              help='An adaptation made elsewhere, to check instead of adapting.')
@click.option('--adapter', 'adapter_spec',
              help='module:callable taking the prompt and returning the adapted text.')
@click.option('--glosbe/--no-glosbe', default=True, show_default=True,
              help='Look up new and target words on Glosbe when offline sources have no gloss.')
@click.option('--out', 'out_path', type=click.Path(dir_okay=False), help='Write JSON here instead of stdout.')
@click.option('--strict', is_flag=True, help='Exit 1 when the text fails a check.')
def build(source, vocab_path, frequent_path, kaikki_path, adapted_path, adapter_spec, glosbe, out_path, strict):
    """Turn an article (URL, .html or .txt) into a checked reading text with targets and glosses."""
    if adapted_path and adapter_spec:
        raise click.UsageError('use --adapted or --adapter, not both')
    dictionary = KaikkiDictionary.load(kaikki_path) if kaikki_path else None
    vocabulary = Vocabulary.from_file(vocab_path, frequent_path, lemmatizer=dictionary)
    resolver = GlossResolver(vocabulary, dictionary, glosbe=_glosbe if glosbe else None, glosbe_delay=0.5)
    article = article_mod.load(source)
    if not article.text:
        raise click.ClickException(f'no article text found in {source}')

    result = build_text(
        article,
        vocabulary,
        resolver=resolver,
        adapter=_load_adapter(adapter_spec) if adapter_spec else None,
        supplied_text=Path(adapted_path).read_text(encoding='utf-8') if adapted_path else None,
    )
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if out_path:
        Path(out_path).write_text(payload + '\n', encoding='utf-8')
    else:
        click.echo(payload)

    checks = result['adaptation']['checks']
    click.echo(f"origin: {result['adaptation']['origin']}; checks {'passed' if checks['passed'] else 'FAILED'}",
               err=True)
    for r in checks['results']:
        click.echo(f"  {'ok  ' if r['passed'] else 'FAIL'} {r['name']}: {r['detail']}", err=True)
    if strict and not checks['passed']:
        sys.exit(1)


@reader.command()
@click.argument('text_path', type=click.Path(exists=True, dir_okay=False))
@click.argument('transcript_path', type=click.Path(exists=True, dir_okay=False))
@click.option('--pause', 'pause_seconds', type=float, default=DEFAULT_PAUSE_SECONDS, show_default=True,
              help='Silence (seconds) before a word that counts as a pause.')
@click.option('--min-confidence', type=float, default=DEFAULT_MIN_CONFIDENCE, show_default=True,
              help='Mismatches heard with lower confidence are marked unclear, not errors.')
@click.option('--native-seconds', type=float, help='Duration of the native audio, for relative speed.')
@click.option('--json', 'as_json', is_flag=True, help='Print the full result as JSON.')
def compare(text_path, transcript_path, pause_seconds, min_confidence, native_seconds, as_json):
    """Align a transcript (.txt, or .json with word timings) against the text that was read."""
    result = compare_text(Path(text_path).read_text(encoding='utf-8'), load_transcript(transcript_path), pause_seconds=pause_seconds,
                          min_confidence=min_confidence, native_seconds=native_seconds)
    if as_json:
        click.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    click.echo(result.headline)
    if result.wpm:
        speed = f'{result.wpm:g} words a minute'
        if result.relative_speed:
            speed += f' ({result.relative_speed:.0%} of native)'
        click.echo(speed)
    for w in result.stumbles():
        if w.status == 'misread':
            what = f'misread, heard «{w.heard}»'
        elif w.status == 'stress':
            what = f'stress, heard «{w.heard}»'
        elif w.status == 'skipped':
            what = 'skipped'
        else:
            what = ''
        if w.paused:
            what = f'{what}{", " if what else ""}paused {w.pause_before:.1f}s'
        click.echo(f'  {w.index + 1:>3} {w.text}: {what}')
    counts = result.counts
    if counts['repeats'] or counts['extras']:
        click.echo(f"{counts['repeats']} repeated and {counts['extras']} extra words")
    if counts['unclear']:
        click.echo(f"{counts['unclear']} unclear (not counted as errors)")
