# HES Documentation Library v1

## Purpose

Current catalog release: **1.0.6** (2026-11-19). It contains 13 aligned pages in each of the four supported languages.

This package adds a read-only, searchable Documentation section to the existing HES Command Center. It reuses the existing dashboard, locale selector, HTTP handler and static-asset delivery. It does not create a second application or a second source of trading truth.

## Content model

- `catalog.v1.json` is the versioned presentation catalog for Persian, English, German and French.
- Each language contains the same 13 stable document IDs, section counts and safety meaning.
- The curated pages summarize project DNA, product naming, roadmap, Mother architecture, market-data boundary, exchange sequence semantics, timeframe/indicator roles, Risk Gate, training/evaluation, News Radar, journal, operations, troubleshooting and version history.
- `source_register` lists the repository documents used to prepare the summaries.
- `EXCHANGE_SEQUENCE_SEMANTICS_RESEARCH_DIGEST_2026-10-10.md` preserves the key technical conclusions of the user-supplied sequence-semantics report. It is explicitly a digest, not primary exchange evidence.

## Source-of-truth hierarchy

1. Current code, schemas, tests and immutable runtime evidence are the technical truth.
2. Project DNA snapshots and Master Checkpoint documents describe product intent and priorities. The 2026-11-17 DNA snapshot explicitly marks its source verification metadata as unverified and is not a live Notion connection; treat it as a local snapshot and refresh it when the canonical page changes.
3. Exchange primary documentation and recorded official replies define protocol guarantees.
4. This multilingual catalog is a reader-friendly, versioned summary. If it conflicts with a higher-level source, the higher-level source wins and the catalog must be corrected.

The API returns only this curated catalog. It does not traverse arbitrary paths, read secrets, expose private journals or invoke Mother, market-data, execution or write APIs.

## Locale and editorial policy

Supported locales: `fa`, `en`, `de`, `fr`. Persian is right-to-left; English, German and French are left-to-right. Product names, protocol fields, machine enums and exchange identifiers remain stable across languages.

The current copy has been authored and consistency-reviewed in all four languages, with matching page IDs and section structure. This is an AI editorial pass, not an independent native-speaker certification. A native-language reviewer may still identify stylistic refinements; technical meaning and safety wording must not be weakened during such edits.

## Update workflow

1. Identify the authoritative source and its exact revision/hash.
2. Update the canonical technical/project source first; do not use this catalog to overwrite code truth.
3. Update all four locale entries in one change, preserving page IDs and section parity.
4. Run JSON validation and the documentation route tests.
5. Review Persian RTL and the three LTR layouts at desktop and mobile widths.
6. Verify the API's read-only contract and ensure no execution, policy-mutation or journal-write path is introduced.
7. Record catalog version, update date, sources and test evidence.

## Safety contract

`read_only=true`, `execution_enabled=false`, `orders_placed=false`, `policy_mutation=false`. The documentation API is GET-only. Documentation pages explain the product; they cannot authorize trades, alter risk policy, mutate journals or change deployment state.

## Merge and production boundary

The v1.0.6 catalog is delivered through PR #532 from `feat/documentation-library-v1`. Repository merge makes the documentation implementation part of the source tree only; it does not publish or activate the production dashboard. Production release remains a separate gate requiring the approved release manifest, exact-release validation, controlled deployment, health verification and rollback readiness. No documentation change authorizes trading, service restarts or order execution.
