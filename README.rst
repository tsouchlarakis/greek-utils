===========
greek-verbs
===========

Programmable interface to Cooljugator's Modern Greek verb database.

Installation
---------------

.. code-block:: bash

    git clone git@github.com:tsouchlarakis/greek-verbs.git
    rmvirtualenv greek-verbs
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

    greek-verbs show --verb νομίζω
    greek-verbs show --verb νομίζω --verb έχω

**Print necessary information to create an Anki flashcard for a given verb**:

.. code-block:: bash

    greek-verbs anki-flashcard --verb νομίζω

⚓️ Changelog
=============

See `changelog <CHANGELOG.rst>`_.

📜 License
==========

See `license <LICENSE>`_.