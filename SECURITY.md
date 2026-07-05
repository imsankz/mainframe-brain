# Security Policy

## Supported Versions

All releases of Mainframe Brain are currently supported with security updates.

## Reporting a Vulnerability

If you discover a security vulnerability — especially in the redaction layer or any code path that handles sensitive data — **do not open a public issue**.

Email the maintainer directly. Include:

- A description of the vulnerability
- Steps to reproduce
- Affected versions
- Suggested fix (if any)

We will respond within 48 hours and work with you on a coordinated disclosure timeline.

## Security Design

Mainframe Brain has a few security-critical properties:

- **Redaction gate (Layer 3.5):** Nothing reaches an LLM or external API without passing through the redaction layer. SSN-shaped numbers, card numbers, IBAN, routing numbers, and embedded credentials are scrubbed. If you find a pattern the redactor misses, please report it.
- **No secrets in source:** API keys are read from environment variables only (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`). There are no hardcoded credentials in the codebase.
- **Content-hashed caching:** Enrichment cache keys are computed *after* COPY REPLACING expansion and redaction. Code that is structurally identical produces the same hash — no token is spent re-enriching it.

## Scope Limitation

Mainframe Brain is a documentation and knowledge-preservation aid. It is **not** a compliance or audit tool and makes no claims of regulatory authority.

## Dependencies

We recommend pinning dependencies with a lockfile (`pip freeze > requirements.lock`) if you run Mainframe Brain in a production-adjacent environment. CI runs against the latest compatible versions to catch regressions early.
