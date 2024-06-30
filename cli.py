import click

from greek_utils.src.anki_flashcard import anki_flashcard
from greek_utils.src.mantinades_flashcard import mantinades_flashcard
from greek_utils.src.scrape_conjugations import scrape_conjugations
from greek_utils.src.show import show


@click.group()
def cli():
    """
    Command line interface for greek-utils.
    """
    pass


cli.add_command(scrape_conjugations)
cli.add_command(show)
cli.add_command(anki_flashcard)
cli.add_command(mantinades_flashcard)


def main(args=None):
    cli()
