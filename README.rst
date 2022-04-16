===========
greek-verbs
===========

Programmable interface to Cooljugator's Modern Greek verb database.

Installation
---------------

Prerequisites

- Python 3.6+
- ``pip``
- (optional) ``virtualenvwrapper``

.. code-block:: bash

    git clone git@github.com:tsouchlarakis/greek-verbs.git
    rmvirtualenv greek-verbs  # Only if using virtualenvwrapper to manage virtualenvs
    mkvirtualenv greek-verbs
    workon greek-verbs
    cd greek-verbs
    pip install -r requirements.in
    pip install -e .

Usage
-----

**Scrape the Cooljugator website for all Modern Greek verb conjugations**:

.. code-block:: bash

    greek-verbs scrape-conjugations --json-output-fpath ~/Desktop/verb_conjugations.json

**Show data for a given verb or verbs**:

.. code-block:: bash

    $ greek-verbs show --verb νομίζω  # Can add an arbitrary number of verbs with --verb verb2 --verb verb3 ...

    +----------------+---------------+-------------+----------------+
    | Present Simple | Future Simple | Past Aorist | Past Imperfect |
    +================+===============+=============+================+
    | νομίζω         | θα νομίσω     | νόμισα      | νόμιζα         |
    +----------------+---------------+-------------+----------------+
    | νομίζεις       | θα νομίσεις   | νόμισες     | νόμιζες        |
    +----------------+---------------+-------------+----------------+
    | νομίζει        | θα νομίσει    | νόμισε      | νόμιζε         |
    +----------------+---------------+-------------+----------------+
    | νομίζουμε      | θα νομίσουμε  | νομίσαμε    | νομίζαμε       |
    +----------------+---------------+-------------+----------------+
    | νομίζετε       | θα νομίσετε   | νομίσατε    | νομίζατε       |
    +----------------+---------------+-------------+----------------+
    | νομίζουν       | θα νομίσουν   | νόμισαν     | νόμιζαν        |
    +----------------+---------------+-------------+----------------+

    +------------------------------+----------------------------+
    | Imperative Imperfective Mood | Perfective Imperative Mood |
    +==============================+============================+
    | νόμιζε                       | νόμισε                     |
    +------------------------------+----------------------------+
    | νομίζετε                     | νομίσετε                   |
    +------------------------------+----------------------------+

    Ελλήνικα: ... \# first example usage in Greek
    English: ... \# second example usage in Greek

    ...more example usages

**Print necessary information to create an Anki flashcard for a given verb**:

.. code-block:: bash

    $ greek-verbs anki-flashcard --verb νομίζω

    Front
    =====
    νομίζω

    Back
    ====
    | Present (simple) | Future (simple) | Past (aorist) | Past (imperf.)
    εγω | νομίζω | θα νομίσω | νόμισα | νόμιζα
    εσυ | νομίζεις | θα νομίσεις | νόμισες | νόμιζες
    αυτ(ος/ή/ό) | νομίζει | θα νομίσει | νόμισε | νόμιζε
    εμείς | νομίζουμε | θα νομίσουμε | νομίσαμε | νομίζαμε
    εσείς | νομίζετε | θα νομίσετε | νομίσατε | νομίζατε
    αυτ(οί/ές/ά) | νομίζουν | θα νομίσουν | νόμισαν | νόμιζαν

    | Imperative (imperf. mood) | Imperative (perf. mood)
    εσυ | νόμιζε | νόμισε
    εσείς | νομίζετε | νομίσετε

Changelog
---------

See `changelog <CHANGELOG.rst>`_.

License
-------

See `license <LICENSE>`_.