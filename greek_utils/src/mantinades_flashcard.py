import click

import pandas as pd
import pyperclip
import subprocess


def show_macos_dialog(message):
    script = f'display dialog "{message}" with title "Mantinades Flashcard"'
    subprocess.run(["osascript", "-e", script])


@click.command()
def mantinades_flashcard():
    """
    Build an Anki import file containing flashcards for one or more mantinades copied
    to clipboard. If multiple mantinades are copied, each one will be a row in the import
    file, which will result in separate cards in Anki. Each mantinada must be separated by
    a newline, e.g.:

    Mantinada 1 line 1
    Mantinada 1 line 2,
    Mantinada 1 line 3
    Mantinada 1 line 4.

    Mantinada 2 line 1
    Mantinada 2 line 2,
    Mantinada 2 line 3
    Mantinada 2 line 4.

    Note the required formatting with the comma at the end of line 2, and the period
    at the end of line 4.
    """
    try:
        clipboard_content = pyperclip.paste().strip()
        if not clipboard_content:
            raise ValueError('Clipboard is empty. Copy one or more mantinades to clipboard and try again.')

        anki_import_df = pd.DataFrame(columns=['front', 'back'])

        mantinades_lst = clipboard_content.split('\n\n')
        for mantinada_str in mantinades_lst:
            lines = [x.strip() for x in mantinada_str.split('\n')]
            if len(lines) != 4:
                raise ValueError(f'Invalid mantinada format. Expected 4 lines, but got {len(lines)} for mantinada: {mantinada_str}.')

            if not lines[1].endswith(','):
                raise ValueError(f'Expected a comma at the end of line 2 of mantinada: {mantinada_str}.')

            valid_line_endswith_punct = ['.', '!']
            if not any([lines[3].endswith(p) for p in valid_line_endswith_punct]):
                raise ValueError(f'Expected a period at the end of line 4 of mantinada {mantinada_str}.')

            # Format is correct
            front = lines[0] + '...'
            back = '<br>'.join(lines)
            anki_import_df.loc[len(anki_import_df)] = [front, back]

        anki_import_df.to_csv('/Users/Andoni/Desktop/mantinades_import.csv', index=False, header=False, sep=';')

    except Exception as e:
        show_macos_dialog('Error: ' + str(e))
        raise e
