import click

from greek_utils.mantinades_flashcard import mantinades_flashcard
from greek_utils.scrape_conjugations import scrape_conjugations
from greek_utils.show import show
from greek_utils.verb_flashcard import verb_flashcard


@click.group()
def cli():
    """
    Command line interface for greek-utils.
    """
    pass


cli.add_command(scrape_conjugations)
cli.add_command(show)
cli.add_command(verb_flashcard)
cli.add_command(mantinades_flashcard)


def main(args=None):
    cli()
