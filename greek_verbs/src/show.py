import click
import json
import termtables as tt
from os.path import dirname, join


def print_conjugation_table(conjugation: dict) -> None:
    """
    Build conjugation table given conjugation dictionary.
    """
    conj_dct = {
        'present_simple': [
            conjugation['present_simple_1sg'],
            conjugation['present_simple_2sg'],
            conjugation['present_simple_3sg'],
            conjugation['present_simple_1pl'],
            conjugation['present_simple_2pl'],
            conjugation['present_simple_3pl'],
        ],
        'future_simple': [
            conjugation['future_simple_1sg'],
            conjugation['future_simple_2sg'],
            conjugation['future_simple_3sg'],
            conjugation['future_simple_1pl'],
            conjugation['future_simple_2pl'],
            conjugation['future_simple_3pl'],
        ],
        'past_aorist': [
            conjugation['past_aorist_1sg'],
            conjugation['past_aorist_2sg'],
            conjugation['past_aorist_3sg'],
            conjugation['past_aorist_1pl'],
            conjugation['past_aorist_2pl'],
            conjugation['past_aorist_3pl'],
        ],
        'past_imperfect': [
            conjugation['past_imperfect_1sg'],
            conjugation['past_imperfect_2sg'],
            conjugation['past_imperfect_3sg'],
            conjugation['past_imperfect_1pl'],
            conjugation['past_imperfect_2pl'],
            conjugation['past_imperfect_3pl'],
        ],
    }

    tt.print(
        [
            [conj_dct['present_simple'][0], conj_dct['future_simple'][0], conj_dct['past_aorist'][0], conj_dct['past_imperfect'][0]],
            [conj_dct['present_simple'][1], conj_dct['future_simple'][1], conj_dct['past_aorist'][1], conj_dct['past_imperfect'][1]],
            [conj_dct['present_simple'][2], conj_dct['future_simple'][2], conj_dct['past_aorist'][2], conj_dct['past_imperfect'][2]],
            [conj_dct['present_simple'][3], conj_dct['future_simple'][3], conj_dct['past_aorist'][3], conj_dct['past_imperfect'][3]],
            [conj_dct['present_simple'][4], conj_dct['future_simple'][4], conj_dct['past_aorist'][4], conj_dct['past_imperfect'][4]],
            [conj_dct['present_simple'][5], conj_dct['future_simple'][5], conj_dct['past_aorist'][5], conj_dct['past_imperfect'][5]],
        ],
        header=['Present Simple', 'Future Simple', 'Past Aorist', 'Past Imperfect'],
        style=tt.styles.ascii_thin_double,
        padding=(0, 1),
        alignment='llll'
    )


def print_imperative_table(conjugation: dict) -> str:
    """
    Build imperative table, if it exists, given conjugation dictionary.
    """
    is_imperative_table_present = \
        conjugation['imperative_imperfect_mood_2sg'] > '' \
        or conjugation['imperative_imperfect_mood_2pl'] > '' \
        or conjugation['imperative_perfect_mood_2sg'] > '' \
        or conjugation['imperative_perfect_mood_2pl'] > ''

    if is_imperative_table_present:
        conj_dct = {
            'imperative_imperfect_mood': [
                conjugation['imperative_imperfect_mood_2sg'],
                conjugation['imperative_imperfect_mood_2pl'],
            ],
            'imperative_perfective_mood': [
                conjugation['imperative_perfect_mood_2sg'],
                conjugation['imperative_perfect_mood_2pl'],
            ],
        }

        print()
        tt.print(
            [
                [conj_dct['imperative_imperfect_mood'][0], conj_dct['imperative_perfective_mood'][0]],
                [conj_dct['imperative_imperfect_mood'][1], conj_dct['imperative_perfective_mood'][1]],
            ],
            header=['Imperative Imperfective Mood', 'Perfective Imperative Mood'],
            style=tt.styles.ascii_thin_double,
            padding=(0, 1),
            alignment='ll'
        )


def print_example_usages(example_usages: dict, num_examples: int) -> None:
    """
    Print example usages if present.
    """
    if len(example_usages):
        for i, (greek, english) in enumerate(example_usages.items()):
            if i == num_examples: break
            print()
            print(f'Ελλήνικα: {greek}\nEnglish: {english}')


@click.option('--verb', type=str, required=True, multiple=True,
              help='Verb to search for and display.')
@click.option('--conjugations-json', type=str, default=join(dirname(dirname(dirname(__file__))), 'verb_conjugations.json'),
              help='Path to conjugations JSON file.')
@click.option('--num-examples', type=int, default=None,
              help='Configurable number to limit the number of examples displayed')


@click.command()
def show(verb: tuple, conjugations_json: str, num_examples: int) -> None:
    """
    Print a given verb to the console.
    """
    with open(conjugations_json, 'r') as f:
        verb_conjugations = json.load(f)

    verb = [x.lower() for x in list(verb)]
    for verb_name in verb:
        if verb_name in verb_conjugations:
            verb_info = verb_conjugations[verb_name]

            conjugation = verb_info['conjugation']
            print_conjugation_table(conjugation)
            print_imperative_table(conjugation)
            print_example_usages(verb_info['example_usages'], num_examples)

        else:
            raise KeyError(f'Verb "{verb_name}" not found in conjugations JSON file.')
