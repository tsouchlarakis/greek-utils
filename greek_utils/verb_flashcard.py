import click

import json
import logging
import pyperclip
import re
import urllib.parse
from os.path import dirname, join

import requests
from bs4 import BeautifulSoup

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

def scrape_glosbe_translation(word: str) -> list:
    """
    Scrape glosbe.com for English translations of a Greek word. Returns a list
    of translation strings (empty list if none found).

    NOTE: requests/bs4/urllib.parse are imported at module top (not inside this
    function) because greek_utils.helpers.logger_setup() installs a global
    ExtendedLogger class; importing urllib3 after that makes its internal
    log.debug() calls crash inside _build_message().
    """
    url = f'https://glosbe.com/el/en/{urllib.parse.quote(word)}'
    resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
    if resp.status_code != 200:
        return []
    soup = BeautifulSoup(resp.content, 'html.parser')

    # Verified page structure (2026-09-23): the ranked translations are the text
    # of <h3> tags that appear between the <h2>Greek-English dictionary</h2>
    # heading and the NEXT <h2> tag. Other h3/h2 sections on the page (example
    # sentences, phrases, automatic translations) are not translations and must
    # be excluded by only collecting h3 tags in that specific window.
    headings = soup.find_all(['h2', 'h3'])
    translations = []
    in_section = False
    for tag in headings:
        if tag.name == 'h2':
            if in_section:
                break  # left the Greek-English dictionary section
            if tag.get_text(strip=True) == 'Greek-English dictionary':
                in_section = True
        elif tag.name == 'h3' and in_section:
            text = tag.get_text(strip=True)
            if text:
                translations.append(text)
    return translations


@click.option('--verb', type=str, required=True,
              help='Verb to prepare flashcard for.')
@click.option('--conjugations-json', type=str, default=join(dirname(dirname(__file__)), 'verb_conjugations.json'),
              help='Path to conjugations JSON file.')
@click.option('--num-examples', type=int, default=None,
              help='Configurable number to limit the number of examples displayed')
@click.option('--stdout', is_flag=True, default=False,
              help='Print the flashcard to stdout instead of copying it to the clipboard.')
@click.option('--debug', is_flag=True, default=False,
              help='Enable verbose debug logging.')

@click.command()
def verb_flashcard(verb: str, conjugations_json: str, num_examples: int, stdout: bool, debug: bool) -> None:
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

        if stdout:
            print(verb_flashcard_str)
        else:
            pyperclip.copy(verb_flashcard_str)
            print('Flashcard copied to clipboard!')
        logger.debug('Flashcard assembled')
    else:
        translations = scrape_glosbe_translation(verb)
        if translations:
            print(f"'{verb}' not found in conjugations JSON -- used Glosbe translations instead.")
            glosbe_flashcard_str = f'{verb}<br><br>' + ', '.join(translations[:5])
            if stdout:
                print(glosbe_flashcard_str)
            else:
                pyperclip.copy(glosbe_flashcard_str)
                print('Flashcard copied to clipboard!')
        else:
            print(f"No such verb found '{verb}'!")
