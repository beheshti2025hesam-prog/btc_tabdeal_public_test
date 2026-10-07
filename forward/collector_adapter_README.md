# Forward Collector Adapter v1

## Purpose
Provide a branch-safe boundary between fresh Tabdeal observations and the
forward-only runtime.

## Safety boundary
- Does not import the legacy collector.
- Does not execute Git operations.
- Does not push to GitHub.
- Does not write `main`.
- Does not read historical Winner/Survivor populations.
- Disabled by default.
- Rejects runtime use until explicitly enabled by a verified integration.

The existing legacy collector remains separate and must not be run on the
forward branch because its checkpoint path pushes to `origin/main`.

This adapter accepts only contemporaneous observations and preserves sequence
identity for downstream normalization.
