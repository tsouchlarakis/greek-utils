# -*- coding: utf-8 -*-


import _pickle as cPickle
import click
import json
import random
import requests
from bs4 import BeautifulSoup
from os import listdir, makedirs
from os.path import splitext, join, dirname, basename, isdir, expanduser
from send2trash import send2trash
from tqdm import tqdm


base_url = 'https://cooljugator.com/gr'
tmp_verb_data_dpath = join(dirname(__file__), '.tmp_verb_data')


def get_element_by_selector(url: str, selector: str, attr_name: str=None) -> list:
    """
    Extract HTML text by CSS selector from a target URL. Optionally extract an attribute
    specified by `attr_name` from the element selected via `selector`.
    """
    # import html

    page = requests.get(url)
    soup = BeautifulSoup(page.content, 'html.parser')

    if attr_name:
        return [soup.select(selector)[i].attrs[attr_name] for i in range(len(soup.select(selector)))]

    elem = [soup.select(selector)[i].text for i in range(len(soup.select(selector)))]
    return elem


def get_conjugation(base_url: str, verb: str) -> dict:
    """
    Get the Greek conjugation of a given verb.
    """
    selectors = {
        'present_simple_1sg': '#infinitive0 .meta-form',
        'present_simple_2sg': '#present2 .meta-form',
        'present_simple_3sg': '#present3 .meta-form',
        'present_simple_1pl': '#present4 .meta-form',
        'present_simple_2pl': '#present5 .meta-form',
        'present_simple_3pl': '#present6 .meta-form',
        'future_simple_1sg': '#future1 .meta-form',
        'future_simple_2sg': '#future2 .meta-form',
        'future_simple_3sg': '#future3 .meta-form',
        'future_simple_1pl': '#future4 .meta-form',
        'future_simple_2pl': '#future5 .meta-form',
        'future_simple_3pl': '#future6 .meta-form',
        'past_aorist_1sg': '#pastperfect1 .meta-form',
        'past_aorist_2sg': '#pastperfect2 .meta-form',
        'past_aorist_3sg': '#pastperfect3 .meta-form',
        'past_aorist_1pl': '#pastperfect4 .meta-form',
        'past_aorist_2pl': '#pastperfect5 .meta-form',
        'past_aorist_3pl': '#pastperfect6 .meta-form',
        'past_imperfect_1sg': '#pastimperfect1 .meta-form',
        'past_imperfect_2sg': '#pastimperfect2 .meta-form',
        'past_imperfect_3sg': '#pastimperfect3 .meta-form',
        'past_imperfect_1pl': '#pastimperfect4 .meta-form',
        'past_imperfect_2pl': '#pastimperfect5 .meta-form',
        'past_imperfect_3pl': '#pastimperfect6 .meta-form',
        'imperative_imperfect_mood_2sg': '#commandimperfect2 .meta-form',
        'imperative_imperfect_mood_2pl': '#commandimperfect4 .meta-form',
        'imperative_perfect_mood_2sg': '#commandperfect2 .meta-form',
        'imperative_perfect_mood_2pl': '#commandperfect4 .meta-form',
    }

    verb_url = '/'.join([base_url, verb])
    conjugations = {}

    for tense, conjugation_selector in selectors.items():
        conjugation_greek = get_element_by_selector(verb_url, conjugation_selector)
        if len(conjugation_greek) == 1:
            # Conjugation found
            conjugation_greek = conjugation_greek[0]
        elif len(conjugation_greek) == 0:
            # Conjugation not found
            conjugation_greek = ''
        else:
            # Multiple conjugations found - disallowed
            raise Exception(f"Multiple conjugations (ambiguous) found for verb {verb} in tense {tense}")

        conjugations[tense] = conjugation_greek

    return conjugations


def get_example_usages(base_url: str, verb: str) -> dict:
    """
    Scrape example usages of the verb, if any.
    """
    examples_lst = get_element_by_selector(join(base_url, verb), '#example-sentences td')

    if len(examples_lst):
        i = iter(examples_lst)
        examples_dct = dict(zip(i, i))
        return examples_dct
    else:
        return {}


@click.option('--json-output-fpath', type=str, default=join(expanduser('~'), 'Desktop', 'verb_conjugations.json'),
              help='Desired path to output JSON file.')

@click.command()
def scrape_conjugations(json_output_fpath: str) -> None:
    """
    Scrape Cooljugator site for all Modern Greek verb conjugations.
    """
    json_output_fpath = expanduser(json_output_fpath)
    assert splitext(json_output_fpath)[1] == '.json', 'Output file must be a JSON file.'

    # Get universe of verbs to scrape
    with open(join(dirname(__file__),  'verb_list.txt'), 'r') as f:
        full_verb_list = f.read().splitlines()

    # Create temporary directory if not exists, remove it and re-create if it does
    if isdir(tmp_verb_data_dpath):
        send2trash(tmp_verb_data_dpath)

    if not isdir(tmp_verb_data_dpath):
        makedirs(tmp_verb_data_dpath)

    # Load list of verbs already scraped and saved to disk as Pickle files
    already_done = [splitext(f)[0] for f in listdir(tmp_verb_data_dpath) if 'DS_Store' not in f]

    # Filter list of verbs to scrape to only those not already scraped, and shuffle randomly
    scrape_verb_list = [x for x in full_verb_list if x not in already_done]
    random.shuffle(scrape_verb_list)

    # Initialize progress bar
    pbar = tqdm(scrape_verb_list)

    # Scrape each verb and dump each to a temporary .pkl file
    for verb in pbar:
        already_done = [splitext(f)[0] for f in listdir(tmp_verb_data_dpath)]
        if verb not in already_done:
            pbar.set_description(verb)

            verb_data = {}
            verb_data['conjugation'] = get_conjugation(base_url, verb)
            verb_data['example_usages'] = get_example_usages(base_url, verb)

            save_fpath = join(tmp_verb_data_dpath, verb + '.pkl')
            with open(save_fpath, 'wb') as f:
                cPickle.dump(verb_data, f)

    # Load all temporary .pkl files and consolidate all verb data into a single JSON dictionary
    scraped_verb_fpaths = sorted([join(tmp_verb_data_dpath, f) for f in listdir(tmp_verb_data_dpath) if 'DS_Store' not in f])
    all_verb_data = {}
    for verb_fpath in tqdm(scraped_verb_fpaths):
        verb_name = splitext(basename(verb_fpath))[0]
        with open(verb_fpath, 'rb') as f:
            all_verb_data[verb_name] = cPickle.load(f)

    # Save dictionary `all_verb_data` to disk as JSON`
    with open(json_output_fpath, 'w') as f:
        json.dump(all_verb_data, f, ensure_ascii=False)
        print(f'Verb conjugations outputted to: {json_output_fpath}')

    # Remove temporary directory
    if isdir(tmp_verb_data_dpath):
        send2trash(tmp_verb_data_dpath)
