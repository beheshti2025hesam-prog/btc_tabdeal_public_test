# HES Product Naming Standard v1

**Decision date:** 2026-11-17
**Status:** Approved by the product owner
**Scope:** Product identity, user-facing UI labels, documentation and localization

## Canonical names

| Name | Canonical role |
|---|---|
| **HES Trade Agent** | The complete product and trading-agent system. |
| **HES Trade AI** | The intelligent brain and conversational assistant, working with the Mother Orchestrator and specialist agents. |
| **HES Command Center** | The user-facing interface for communication, observation, commands and control. |

These three names describe different layers and must not be used interchangeably.

## User-interface contract

- The product identity remains **HES Trade Agent**.
- The dashboard/workspace is **HES Command Center**.
- The local conversational assistant identifies itself as **HES Trade AI**.
- The assistant's speaker label, chat title, input label, login/entry action and memory messages must use **HES Trade AI**.
- The workspace header and navigation context must identify **HES Command Center**.
- Product names remain stable across languages; explanatory labels and descriptions are localized for Persian, English, German and French.

## Legacy-name compatibility

**HOSHYAR is retired as a user-facing product name.** It may remain temporarily in technical identifiers that already exist, including:

- Python module, class and variable names;
- schema IDs, router IDs and error codes;
- environment-variable names;
- systemd unit and drop-in filenames;
- filesystem paths, SQLite database names and API-key filenames;
- model identifiers, test filenames and historical evidence.

Do not perform a blind global rename. Existing identifiers are compatibility surfaces, not product branding. Any future technical migration must be a separate change with dependency inventory, backward-compatible transition, focused tests, full regression, provenance and an approved rollout/rollback plan.

## Architecture and safety invariants

- Free-first/local open-weight inference remains the rule; no paid or remote LLM fallback.
- The browser/mobile client remains thin; inference stays on the HES VPS.
- Mother evidence readers remain authoritative for HES facts.
- HES Trade AI cannot bypass Data Quality, Confirmation, Risk Gate, `NO_TRADE`, human approval or execution controls.
- HES Command Center remains an interface, not an independent trading authority.
- This naming change does not alter strategy, risk policy, market-data sources, exchange adapters, journal semantics or execution behavior.

## Release boundary

The branding implementation is isolated from the dirty main checkout and from production. It does not enable the local model, install the proposed systemd unit, activate the dashboard drop-in, restart production services, change release pointers or authorize orders. Production activation remains a separate approval and release gate.
