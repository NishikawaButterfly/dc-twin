# ADR 0002: Use a strict versioned JSON boundary for electrical design snapshots

- Status: Accepted
- Date: 2026-08-01
- Decision owners: Project maintainers

## Context

An upstream design application and this simulator have different responsibilities and life cycles. The design system describes a static architecture revision. The simulator applies dynamic scenario events and produces reproducible state evidence. Sharing database tables, ORM classes, authentication internals, or deployment schedules would couple both products and create an unsafe path for proprietary or operational data to leak into a public reference implementation.

The boundary must be language-neutral, reviewable in a pull request, strict enough to reject ambiguous inputs, and evolvable without silently reinterpreting a historical result.

## Decision

Use `ElectricalDesignSnapshot` as a versioned JSON document governed by a JSON Schema in `contracts/electrical-design-snapshot/v1/`.

The boundary has these rules:

- `schema_id` and semantic `schema_version` are required and exact;
- unknown fields are rejected at every defined object level;
- IDs, base units, component states, capacities, connections, and redundancy intent are explicit;
- classification must be `synthetic` in the public application;
- title, creator, method, and assumptions record provenance;
- JSON is decoded with duplicate-key and non-finite-number rejection;
- every reference and topology constraint is validated before simulation;
- canonical UTF-8 JSON is hashed with SHA-256; and
- a breaking semantic change receives a new contract version and migration statement.

Scenario and result envelopes follow the same versioned-contract approach. The simulator does not share an upstream database, ORM, or authentication boundary.

## Consequences

### Positive

- Producers and consumers can validate the same language-neutral artifact.
- Historical inputs remain replayable against an identified engine and contract version.
- Contract diffs are explicit, code-reviewable, and testable with positive and negative fixtures.
- The public repository can enforce a synthetic-only classification and provenance field set.
- Design-authoring and simulation services remain independently deployable.

### Negative

- JSON Schema cannot validate every graph invariant, provenance claim, or real-world engineering fact; semantic validation and human review remain required.
- Strict rejection makes producer drift visible rather than forgiving it, which requires coordinated versioning.
- Large topologies are verbose and remain subject to synchronous resource limits.
- SHA-256 supports identity and replay but does not prove authorship or replace a digital signature.

## Alternatives considered

### Share PostgreSQL tables or ORM models

Rejected. This would couple releases, persistence migrations, privileges, and potentially sensitive data. It would also blur ownership between static design and dynamic simulation records.

### Use unversioned application models

Rejected. Runtime validation alone does not provide an independently reviewable compatibility contract or prevent silent reinterpretation after a code change.

### Use CSV

Rejected. Multiple component subtypes, directed connections, assumptions, provenance, and redundancy groups do not fit one unambiguous flat table without auxiliary conventions.

### Use a binary protocol first

Rejected for the public boundary. A binary format could be efficient but would reduce direct reviewability and add code-generation requirements before scale evidence justifies them.

## Compatibility policy

Additive fields are not automatically compatible because version 1 rejects unknown properties. Any addition requires an explicit schema-version decision. A producer may generate multiple supported versions during migration; the simulator must never guess a version or coerce unsupported fields.

## Verification

Contract tests validate the published examples and rejection corpus. Semantic tests cover uniqueness, reference integrity, DAG enforcement, source-paralleling rules, bounds, and target-kind checks. Replay tests bind snapshot hash, scenario hash, engine version, and computation hash to the stored result.
