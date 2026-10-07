# Forward Journal v1

The Forward Journal is the first operational evidence boundary after Decision.

## Rules
1. Decision records are append-only.
2. LONG, SHORT, and NO_TRADE are all journaled.
3. Future outcomes never rewrite the original decision.
4. Outcomes belong in a separate immutable outcome artifact linked by event_id.
5. Duplicate event_id is rejected.
6. Historical Winner/Survivor populations are not imported.
7. The journal does not execute trades.

## Architecture
Decision → Append-only Decision Journal → Later Outcome Artifact → Forward Evaluation

The existing collector is not wired to this journal yet. This is deliberate:
integration must be done only after writer/branch safety is verified.
