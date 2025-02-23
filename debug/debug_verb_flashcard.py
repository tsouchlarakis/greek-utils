import sys
from os.path import dirname

sys.path.insert(0, dirname(dirname(__file__)))

from greek_utils.verb_flashcard import verb_flashcard

verb_flashcard(['--num-examples', 10, '--verb', 'σοκάρω'])
