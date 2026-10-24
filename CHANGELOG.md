<!-- markdownlint-disable MD024 -->

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- ## V.V.V (YYYY-MM-DD)

### Added

### Changed

### Deprecated

### Removed

### Fixed

### Security -->

## Unreleased

### Added

- `greek_utils.reader` and `greek-utils reader build|compare`: target words from supplied vocabulary states, adaptation prompt and checks (length, new-word ratio, targets, sentence length, numbers, names, quotations), glosses from a kaikki.org extract and Glosbe, and read-aloud transcript alignment (skips, misreads, stress pairs, pauses, reading speed)
- Tests (`pytest`) and `scripts/check.sh` (tests plus `ruff` on the reader package)

### Changed

- Packaging moved to uv: dependencies declared in `pyproject.toml`, locked in `uv.lock`; Python 3.12+ (`.python-version`)

### Removed

- pip-compile `requirements.in` / `requirements.txt`

## 1.1.0 (2025-02-22)

### Added

- Mantinades flashcard
- `num-examples` option in verb flashcard

### Fixed

- Some verb formatting fixes

### Security

## 1.0.0 (2022-04-16)

- Initial utility made available with verb flashcard capability
