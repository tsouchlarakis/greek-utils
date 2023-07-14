import click
from .src.scrape_conjugations import scrape_conjugations
from .src.show import show
from .src.anki_flashcard import anki_flashcard


@click.group()
def cli():
    """
    Command line interface for greek-verbs.
    """
    pass


cli.add_command(scrape_conjugations)
cli.add_command(show)
cli.add_command(anki_flashcard)


def main(args=None):
    cli()
