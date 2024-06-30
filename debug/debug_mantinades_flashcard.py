import sys
from os.path import dirname

sys.path.insert(0, dirname(dirname(__file__)))

from greek_utils.src.mantinades_flashcard import mantinades_flashcard

mantinades_flashcard()
