import click
import json
from os.path import join, dirname


def conjugation_to_md_tables(conj: dict) -> dict:
    """
    Convert the conjugation dictionary output of `get_conjugation()`
    to a Markdown table.
    """
    md_tables = {'main': '', 'imperative': ''}

    main_md_table_string = '\n'.join([
        f"| Present (simple) | Future (simple) | Past (aorist) | Past (imperf.)",
        f"εγω | {conj['present_simple_1sg']} | {conj['future_simple_1sg']} | {conj['past_aorist_1sg']} | {conj['past_imperfect_1sg']}",
        f"εσυ | {conj['present_simple_2sg']} | {conj['future_simple_2sg']} | {conj['past_aorist_2sg']} | {conj['past_imperfect_2sg']}",
        f"αυτ(ος/ή/ό) | {conj['present_simple_3sg']} | {conj['future_simple_3sg']} | {conj['past_aorist_3sg']} | {conj['past_imperfect_3sg']}",
        f"εμείς | {conj['present_simple_1pl']} | {conj['future_simple_1pl']} | {conj['past_aorist_1pl']} | {conj['past_imperfect_1pl']}",
        f"εσείς | {conj['present_simple_2pl']} | {conj['future_simple_2pl']} | {conj['past_aorist_2pl']} | {conj['past_imperfect_2pl']}",
        f"αυτ(οί/ές/ά) | {conj['present_simple_3pl']} | {conj['future_simple_3pl']} | {conj['past_aorist_3pl']} | {conj['past_imperfect_3pl']}",
    ])

    md_tables['main'] = main_md_table_string

    # Imperative table is not required
    is_imperative_table_present = \
        conj['imperative_imperfect_mood_2sg'] > '' \
        or conj['imperative_imperfect_mood_2pl'] > '' \
        or conj['imperative_perfect_mood_2sg'] > '' \
        or conj['imperative_perfect_mood_2pl'] > ''

    if is_imperative_table_present:
        imperative_md_table_string = '\n'.join([
            f"| Imperative (imperf. mood) | Imperative (perf. mood)",
            f"εσυ | {conj['imperative_imperfect_mood_2sg']} | {conj['imperative_perfect_mood_2sg']}",
            f"εσείς | {conj['imperative_imperfect_mood_2pl']} | {conj['imperative_perfect_mood_2pl']}",
        ])

        md_tables['imperative'] = imperative_md_table_string

    return md_tables


def collapse_md_tables(md_tables: dict) -> str:
    """
    Accept the result of `conjugation_to_md_tables()` and format as a string with
    one or both tables, ready to be pasted in to Anki.
    """
    verb_main_table_str = md_tables['main']

    if md_tables['imperative'] > '':
        verb_imperative_table_str = md_tables['imperative']
        verb_all_md_tables_str = '\n\n'.join([verb_main_table_str, verb_imperative_table_str])
    else:
        verb_all_md_tables_str = verb_main_table_str

    return verb_all_md_tables_str


@click.option('--verb', type=str, required=True,
              help='Verb to prepare flashcard for.')
@click.option('--conjugations-json', type=str, default=join(dirname(dirname(dirname(__file__))), 'verb_conjugations.json'),
              help='Path to conjugations JSON file.')

@click.command()
def anki_flashcard(verb: str, conjugations_json: str) -> None:
    """
    Build Anki flashcard for a given verb.
    """
    with open(conjugations_json, 'r') as f:
        verb_conjugations = json.load(f)

    verb = verb.lower()
    if verb in verb_conjugations:
        md_table_str = collapse_md_tables(conjugation_to_md_tables(verb_conjugations[verb]['conjugation']))

        print(f'{verb}')
        print()
        print(f'{md_table_str}')
