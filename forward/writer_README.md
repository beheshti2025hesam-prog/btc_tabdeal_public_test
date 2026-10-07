# Forward Writer v1

Branch-safe persistence boundary.

- No git operations.
- No push.
- No implicit main-branch writes.
- Decisions are delegated to the append-only journal.
- Outcomes are written as new immutable artifacts; decisions are never rewritten.
- Historical Winner/Survivor material is forbidden.
