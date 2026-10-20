# HES Trade Agent — Project DNA

## Team and operating model

The project team consists of exactly two collaborators in its operating plan:

- **Project owner:** the user, who sets priorities and makes project decisions.
- **AI engineering partner:** ChatGPT, which advances technical analysis, implementation planning, code review, test design, evidence checks, and concise reporting.

Do not plan routine project execution around an assumed third team member. The owner has stated that no other person is available to take project actions. Prefer autonomous progress with minimal requests for owner intervention.

## Core architecture — independent market intelligence, venue-only execution

- Market-data candles, charting and analysis come from one documented global provider (TradingView or a comparable public feed). The provider's venue/market identity must remain explicit; do not imply that its price is every execution venue's price.
- Exchange chart candles are not the analytical source of truth. Exchange/private APIs are reserved for order submission, order state, fills, and venue-specific execution constraints.
- Keep the pipeline decoupled: global feed → validated canonical candles → existing strategy/decision and risk gates → venue-specific execution adapter.
- Ordinary candle analysis must not depend on undocumented trade sequence fields. Do not block the candle path on unexplained exchange-volume semantics; preserve source volume unchanged and disable only features that rely on its unresolved meaning.
- Before any execution, explicitly validate source-to-execution symbol mapping, market type, price freshness, spread/basis, tick/step sizes, minimum notional, order type, fees, slippage, margin/leverage, and duplicate/unknown order outcomes. A global chart price is not proof of an executable venue price.
- No live order is allowed until a concrete venue adapter and its order/fill reconciliation tests are proven. Public market-data work requires no account credentials; never infer authorization to trade from read-only data access.
- The repository has no verified frontend entry point. Reuse an authorized existing frontend if found. Do not invent one or create a parallel app without an explicit, documented architecture decision.

## Review and evidence policy

- ChatGPT performs a careful technical review, but must never misrepresent its own review as an independent third-party human review.
- Automated CI and tests provide repeatable evidence only for the exact commit and test scope actually run. A prior green run does not prove a later change.
- Tie reported CI results, artifacts, hashes, and claims to verifiable commit identifiers and source evidence.
- Distinguish clearly between completed work, proposed work, unverified assumptions, and blockers.
- Do not claim local tests ran if the required test command or dependencies were unavailable.
- If a repository branch-protection rule or external requirement mandates a human approval, report it honestly as a repository/policy constraint. Do not fabricate an approval or imply an unavailable person will act. Continue all work that can safely proceed without that approval.

## Security and release discipline

- No security gate passes on confidence, a green CI badge, or a hash alone; it passes only when its stated security properties are demonstrated by evidence.
- Keep HOLD for the affected security-sensitive release path until its required evidence is established.
- Do not enable live collection, exchange account access, VPS changes, or trading as an implicit consequence of documentation or test work.
- Prefer automation, adversarial tests, reproducible checks, and least-privilege operations while keeping the project owner informed of material decisions.

## Communication

Report in plain language, briefly and accurately. State what changed, the exact evidence, remaining uncertainty, and the next concrete action. Never overstate tool access or claim a GitHub change succeeded until its result is confirmed.
