# Security Policy

## Supported versions

Security fixes are provided for the latest release on the `main` branch. This project is an early-stage reference implementation; no long-term support window is promised yet.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub's private vulnerability-reporting feature for this repository. If that feature is unavailable, use a private contact method listed on the maintainer's GitHub profile and first request a secure channel without sending exploit details. Include:

- the affected version or commit;
- the smallest reproducible proof of concept;
- expected and observed behavior;
- impact and realistic preconditions; and
- any suggested mitigation.

Please avoid accessing data that does not belong to you, degrading a service, or publishing details before a fix is available. Receipt should be acknowledged within five business days. Timing for triage and remediation depends on severity and maintainer availability.

## Deployment boundary

The reference deployment is designed for local evaluation with synthetic data. It does not provide end-user authentication, authorization, tenant isolation, rate limiting, or an internet-facing TLS endpoint. Do not expose it directly to an untrusted network.

A production integrator must place the API behind an authenticated reverse proxy or gateway, enforce least-privilege network rules, terminate TLS, configure request-size and rate limits, protect database credentials in a secret manager, and establish log retention and incident-response procedures.

## Data boundary

Only fictional, synthetic examples belong in this public repository. Do not submit customer names, facility identifiers, network addresses, credentials, exports from building-management or SCADA systems, or topology data derived from a real site. See [Data Provenance](docs/DATA_PROVENANCE.md).

## Security-relevant model limitations

The simulator does not connect to, monitor, or control physical equipment. Its outputs must not be used as switching instructions, protection settings, emergency procedures, or evidence of regulatory compliance. See [Model Specification](docs/MODEL_SPECIFICATION.md).
