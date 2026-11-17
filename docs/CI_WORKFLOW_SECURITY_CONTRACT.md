# CI workflow security contract

## Immutable action dependencies

Every external GitHub Action in `.github/workflows/` must use a full 40-character commit SHA. A human-readable version tag may appear only as a trailing YAML comment, for example `uses: actions/checkout@<commit-sha> # v7`. Repository-local composite actions (`./.github/actions/...`) are tied to the checked-out commit and are exempt.

`python scripts/check_workflow_action_pins.py` enforces this policy. It runs in the canonical local regression script, the main GitHub regression workflow, and the Actions execution canary. A mutable tag, branch name, short SHA, or missing ref fails closed.

## Updating an action

1. Confirm the release and repository from the action owner's official GitHub repository.
2. Resolve the exact version tag to its commit with `git ls-remote https://github.com/<owner>/<repo>.git refs/tags/<tag>`; for annotated tags, resolve the peeled `^{}` commit.
3. Update every occurrence of that action in one change and keep the version tag as a comment.
4. Review the action's release notes and permissions; preserve least-privilege workflow token scopes.
5. Run the action canary, the workflow-pin policy, and exact-head regression/browser checks before merge.

The checked-in workflow SHAs are intentionally immutable. Upstream tag movement or a new major release must never silently change the build toolchain.
