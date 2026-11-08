# Changelog

All notable changes are documented here. This project follows [Semantic Versioning](https://semver.org/) and the structure of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- The capacity allocation now treats sources as two classes and solves each interval in two stages: every load from the live sources (available utilities and running generators) first, then, only for demand still short, the same loads with the battery edges added. A UPS therefore never discharges while a live source can reach the load, and supplies exactly the demand no live source can reach. Both stages remain deterministic, so results stay reproducible. Every eligible source is now reported in `source_power_w`, including at `0 W` and including in intervals with zero demand.
- The wheel and sdist metadata declare the license as the SPDX expression `MIT` (`License-Expression`, PEP 639) instead of the full text of `LICENSE` in the deprecated `License` field, and drop the deprecated `License :: OSI Approved :: MIT License` classifier. `LICENSE` is still listed as `License-File` and ships in both archives.

### Fixed

- A scenario whose first solved state is already under-served now raises `load_unserved` at `0 ms` against the `system.initialized` transition, with the same code and severity as a later raise, and clears normally when service returns. Such runs previously reported an empty alarm list for the whole horizon. No bundled reference scenario begins under-served, so every published reference hash is unchanged.
- A battery is no longer drained in preference to a live utility feed that could reach the load. The previous single-pass allocation pooled both source classes and took the shortest augmenting path, so on a healthy 2N topology the loss of feed A discharged UPS A to empty while utility B delivered 0 W. All five bundled reference results, including their computation hashes, are byte-identical; the worked examples in `docs/user-guide/` that demonstrated the defect were re-baselined.
- The committed OpenAPI contract, `contracts/openapi/v1/openapi.json`, now matches the document the API serves. It had kept the title "Data Center Electrical Digital Twin" after the API was renamed "dc-twin electrical simulator" for 0.2.0, because CI regenerated the file without comparing it with the committed copy. CI now runs `scripts/generate_openapi.py --check`, which compares the file byte for byte with the document the API generates, fails whenever they differ, and ends its report with the command that regenerates the file. It reports a missing file, and names three differences on lines of their own: bytes that are not UTF-8, a UTF-8 byte order mark at the start, and CRLF or CR line endings. Any other difference appears in a unified diff from the committed file to the generated document. The diff shows its lines as they are when each of them is printable ASCII with no backslash and no space at its end; otherwise it shows every line escaped, and a line before it says how: a backslash as `\\`, a space at the end of a line as `\u0020`, and a character outside printable ASCII as `\uNNNN` (`\UNNNNNNNN` above U+FFFF). Bytes that are not UTF-8 appear in it as `\xNN`. The test suite makes the same byte comparison, and checks that the running API serves the committed document at `/api/v1/openapi.json`, failing with a unified diff of the two when it does not. `.gitattributes` keeps the file's LF line endings on every checkout.

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
