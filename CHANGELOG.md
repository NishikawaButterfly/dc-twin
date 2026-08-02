# Changelog

All notable changes are documented here. This project follows [Semantic Versioning](https://semver.org/) and the structure of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.2.0] - 2026-08-02

### Added

- Synthetic N and N+1 reference topologies, each with one hand-calculated scenario: a single-path utility loss with UPS ride-through to depletion, and an absorbed single-UPS failure with a bounded reserve battery bridge.
- A side-by-side scenario comparison in the web explorer, with a merged milestone table showing where two runs diverge.
- A plain-language explainer for readers without an electrical background.
- A public demo of the reference explorer.

### Changed

- The project presents itself as a deterministic reference simulator; the explorer and API titles match.

### Fixed

- Web assets are served with explicit media types, so the explorer also works on hosts whose registry maps .js to text/plain.

## [0.1.0] - 2026-08-01

### Added

- Deterministic active-power capacity simulation core.
- Strict versioned snapshot, scenario, and result contracts.
- Synthetic 2N reference topology and three reproducible scenarios.
- Traceable timelines with alarms, synthetic telemetry, state hashes, and metric explanations.
- Versioned HTTP API and PostgreSQL persistence.
- Static interactive explorer, containers, and continuous integration.
- Architecture, model, security, provenance, operations, and test documentation.

### Security

- Synthetic-only public data policy.
- Explicit non-control deployment boundary.

[Unreleased]: https://github.com/NishikawaButterfly/dc-twin/commits/main
