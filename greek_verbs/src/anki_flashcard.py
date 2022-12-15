import click
import json
from os.path import join, dirname


class Attribute():
    pass


def conjugation_to_html(verb: str, conj: dict) -> str:
    """
    Convert the conjugation dictionary output of `get_conjugation()`
    to HTML that will populate the Anki flashcard and will be automatically
    parsed by Anki in tabular format.
    """
    vars = Attribute()
    for k, v in conj.items():
        setattr(vars, k, v)

    conj = vars
    del vars

    with open(join(dirname(__file__), 'anki_flashcard_template.html'), 'r') as f:
        html_template = f.read()
        html_template = html_template.format(**locals())

    return html_template


def format_example_usages(conj: dict, example_usages: dict, num_examples) -> str:
    """
    Extract example usages from the conjugation and format them for
    an Anki flashcard. The input is a dictionary with key:value pairs
    of Greek:English for each example usage.
    """
    if len(example_usages):

        template = '{greek}<br><em>{english}</em>'

        usages = []

        for i, (greek, english) in enumerate(example_usages.items()):
            if i == num_examples: break
            clean_usage = lambda x: x.replace('#', '').strip().strip('-').strip().strip('"').strip()

            greek = clean_usage(greek)
            english = clean_usage(english)
            usage = template.format(greek=greek, english=english)

            for conj_name, conj_realization in conj.items():
                usage = usage.replace(conj_realization, f'<b>{conj_realization}</b>')

            usages.append(usage)

        usages_str = '<br><br>'.join(usages)
        return usages_str
    else:
        return ''


@click.option('--verb', type=str, required=True,
              help='Verb to prepare flashcard for.')
@click.option('--conjugations-json', type=str, default=join(dirname(dirname(dirname(__file__))), 'verb_conjugations.json'),
              help='Path to conjugations JSON file.')
@click.option('--num-examples', type=int, default=None,
              help='Configurable number to limit the number of examples displayed')


@click.command()
def anki_flashcard(verb: str, conjugations_json: str, num_examples: int) -> None:
    """
    Build Anki flashcard for a given verb.
    """
    with open(conjugations_json, 'r') as f:
        verb_conjugations = json.load(f)

    verb = verb.lower()
    if verb in verb_conjugations:
        conjugation_table_str = conjugation_to_html(verb, verb_conjugations[verb]['conjugation'])
        example_usage_str = format_example_usages(verb_conjugations[verb]['conjugation'], verb_conjugations[verb]['example_usages'], num_examples)

        anki_flashcard_str = verb
        anki_flashcard_str += '<br><br>'
        anki_flashcard_str+= conjugation_table_str
        if len(example_usage_str) > 0:
            anki_flashcard_str += '<br>'
            anki_flashcard_str += example_usage_str

        print(f'{anki_flashcard_str}')
    else:
        print(f"No such verb found '{verb}'!")
