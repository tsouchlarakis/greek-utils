import click

import json
import logging
import pyperclip
import re
from os.path import dirname, join

from greek_utils.helpers import logger_setup


class Attribute():
    pass


def conjugation_to_html(conj: dict, logger: logging.Logger) -> str:
    """
    Convert the conjugation dictionary output of `get_conjugation()`
    to HTML that will populate the Anki flashcard and will be automatically
    parsed by Anki in tabular format.
    """
    logger.debug('Formatting conjugation dictionary to HTML')

    vars = Attribute()
    for k, v in conj.items():
        setattr(vars, k, v)

    conj = vars
    del vars

    with open(join(dirname(__file__), 'templates', 'verb_flashcard_template.html'), 'r') as f:
        html_template = f.read()
        html_template = html_template.format(**locals())

    logger.debug('Created conjugation HTML')
    return html_template


def format_example_usages(conj: dict, example_usages: dict, num_examples: int, logger: logging.Logger) -> str:
    """
    Extract example usages from the conjugation and format them for
    an Anki flashcard. The input is a dictionary with key:value pairs
    of Greek:English for each example usage.
    """
    if len(example_usages):
        logger.debug(f'Formatting {len(example_usages)} example usages as HTML')
        template = '{greek}<br><em>{english}</em>'

        usages = []
        for i, (greek, english) in enumerate(example_usages.items()):
            logger.debug(f'Example usage {i}', arrow='black')

            if i == num_examples: break
            clean_usage = lambda x: x.replace('#', '').strip().strip('-').strip().strip('"').strip()

            logger.debug(f'Greek "{greek}"', arrow='black', indent=1)
            greek = clean_usage(greek)
            logger.debug(f'Greek (cleaned) "{greek}"', arrow='black', indent=1)
            logger.debug(f'English "{english}"', arrow='black', indent=1)
            english = clean_usage(english)
            logger.debug(f'English (cleaned) "{english}"', arrow='black', indent=1)
            usage = template.format(greek=greek, english=english)
            logger.debug(f'Sample usage "{usage}"', indent=1)

            verb_inflections = sorted(list(set([x for x in conj.values() if x > ''])), key=lambda x: (-len(x), x))
            for inflection in verb_inflections:
                m = re.search(rf'(?<!>)\b{inflection}\b(?!<)', usage)
                if m:
                    logger.debug(f'Bolding "{inflection}" in usage', indent=1)
                    usage = usage[:m.start()] + f'<b>{inflection}</b>' + usage[m.end():]

            usages.append(usage)

        usages_str = '<br><br>'.join(usages)
        logger.debug('Created example usages HTML')
        return usages_str
    else:
        logger.debug('No example usages found')
        return ''

@click.option('--verb', type=str, required=True,
              help='Verb to prepare flashcard for.')
@click.option('--conjugations-json', type=str, default=join(dirname(dirname(__file__)), 'verb_conjugations.json'),
              help='Path to conjugations JSON file.')
@click.option('--num-examples', type=int, default=None,
              help='Configurable number to limit the number of examples displayed')
@click.option('--debug', is_flag=True, default=False,
              help='Enable verbose debug logging.')

@click.command()
def verb_flashcard(verb: str, conjugations_json: str, num_examples: int, debug: bool) -> None:
    """
    Build Anki flashcard for a given verb.
    """
    logging_level = logging.DEBUG if debug else logging.ERROR
    logger = logger_setup(name='verb_flashcard', level=logging_level)
    logger.debug(f"Creating Anki flashcard for '{verb}'")

    with open(conjugations_json, 'r') as f:
        logger.debug(f'Loading verb conjugations at "{conjugations_json}"')
        verb_conjugations = json.load(f)

    verb = verb.lower()
    if verb in verb_conjugations:
        conjugation_table_str = conjugation_to_html(
            conj=verb_conjugations[verb]['conjugation'],
            logger=logger,
        )
        example_usage_str = format_example_usages(
            conj=verb_conjugations[verb]['conjugation'],
            example_usages=verb_conjugations[verb]['example_usages'],
            num_examples=num_examples,
            logger=logger,
        )

        logger.debug('Assembling flashcard')

        verb_flashcard_str = verb
        verb_flashcard_str += '<br><br>'
        verb_flashcard_str+= conjugation_table_str

        if len(example_usage_str) > 0:
            verb_flashcard_str += '<br>'
            verb_flashcard_str += example_usage_str

        pyperclip.copy(verb_flashcard_str)
        print('Flashcard copied to clipboard!')
        logger.debug('Flashcard assembled')
    else:
        print(f"No such verb found '{verb}'!")
