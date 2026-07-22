# Research Reach Project Instructions

## Purpose

Research Reach is a three-stage, file-oriented research workflow: reviewed Opening, isolated network Search, and networkless Synthesis.

## Commands

- Install CLI and companion skills: `pwsh ./scripts/bootstrap.ps1`
- Run tests from source: `$env:PYTHONPATH = 'src'; python -m unittest discover -v`
- Source changes are not live until bootstrap reinstalls the user-level package.

## Stack And Layout

- Python 3.11+ with setuptools; runtime package lives in `src/research_reach/`.
- CLI entry points are declared in `pyproject.toml`.
- Companion skills live in `skills/`; regression tests live in `tests/`.
- Generated work packages belong under ignored `work/` and are not source documentation.

## Stable Contracts

- Never confirm a brief without explicit user approval of the exact revision.
- Search uses one network-enabled isolated Worker per confirmed topic; Synthesis is networkless.
- Keep raw private local data out of network Workers. Produce a local de-identified aggregate and reference it with a safe relative `artifact://` URL.
- Strict output schemas must require every declared object property, including nullable fields, and must avoid unsupported keywords such as `uniqueItems`.
- Keep raw Worker stderr private; public errors may include only bounded structured upstream messages.

## Current Verification

- Run the full test suite, bootstrap, compare installed/source module hashes, and perform CLI smoke checks before calling a runtime fix complete.
