# Contributing

Thank you for improving the Data Center Electrical Digital Twin. Contributions should preserve the project's central properties: deterministic execution, explicit units, strict contracts, traceable results, and synthetic-only public data.

## Before you start

- Open an issue before a large behavioral or contract change.
- Keep one concern per pull request.
- Never contribute data from a real facility, customer, tender, monitoring system, or incident.
- Do not present modeled capacity results as AC power-flow, protection, certification, or control-system outputs.

## Local workflow

This project requires Python 3.12 or 3.13. Create an isolated environment, then install the project using the dependency groups declared in `pyproject.toml`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test,release]"
```

Run the same focused checks used by CI:

```powershell
ruff format --check --diff .
ruff check .
mypy src
pytest --cov=dc_twin --cov-branch --cov-report=term-missing
python -m build
twine check dist\*
pip-audit
```

Do not commit virtual environments, generated results, database volumes, credentials, or local environment files.

## Contracts and compatibility

Input and output files must validate against the JSON Schemas in `contracts/`. Contract changes require:

1. an architecture decision record;
2. new or updated positive and negative contract tests;
3. regenerated synthetic examples;
4. API and model-documentation updates; and
5. an explicit compatibility and migration statement.

Breaking changes use a new contract directory and schema version. Existing versioned contracts are not silently reinterpreted.

## Determinism and test evidence

Every behavioral change should include a test that proves the intended result and a failure-path test where applicable. Reference-scenario metrics must also be checked against the hand calculations in [Reference Scenario](docs/REFERENCE_SCENARIO.md). Replaying identical canonical inputs with the same engine version must produce the same computation hash.

## Pull requests

Use an imperative commit subject and explain:

- the problem and scope;
- contract or persistence impact;
- security and data-provenance impact;
- validation performed; and
- known limitations or follow-up work.

By contributing, you agree that your contribution is licensed under the MIT License and that you will follow the [Code of Conduct](CODE_OF_CONDUCT.md).
