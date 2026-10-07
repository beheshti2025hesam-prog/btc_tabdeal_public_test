# Policy Activation Gate v1

The activation gate is a hard safety boundary.

A policy/ruleset must explicitly be ACTIVE before forward runtime can consume it.
Draft, incomplete, historically tuned, future-leaking, or execution-enabled
configurations are rejected.

This gate does not decide whether a strategy is profitable. It only decides
whether the configuration is structurally eligible to enter a forward run.
