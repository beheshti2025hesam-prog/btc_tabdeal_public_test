# Decision Layer v1

Final forward-only decision boundary.

Inputs: Opportunity Candidate, Confirmation, Risk Gate.
Outputs: LONG, SHORT, NO_TRADE.

The resolver fails closed on missing, unknown, failed, or direction-conflicting gates.
It never places orders and never uses historical Winner/Survivor records or future outcomes.
