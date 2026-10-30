# HES multi-market extension boundary v1

This is an isolation contract, not a claim that every asset class is already connected.

## Reuse the existing core
New providers must implement the existing `NativeOHLCVSource` boundary and emit the existing `NativeOHLCVBatch` contract. Do not create a second chart, candle, feature, or signal engine.

## Market-specific semantics remain separate
- Crypto Spot: Gate.io is the canonical provider for the current release. BTC_USDT remains strategy-approved; ETH_USDT and SOL_USDT are observation-only candidates.
- FX: disabled until an entitled real-time provider, timezone/session calendar, bid/ask spread, holiday, and rollover contract are qualified.
- US equities: disabled until real-time entitlement, exchange calendar, split/dividend adjustment, corporate-action provenance, and volume semantics are qualified.
- Iran equities: disabled until an official domestic source, legal access, local session/auction/price-limit rules, and data semantics are qualified.
- Commodities: disabled until a provider and contract expiry/roll semantics are qualified.

## Safety boundary
Every profile is disabled by default outside its explicitly qualified scope. No profile can borrow another market's calendar, volume interpretation, symbol mapping, or execution adapter. The Gate.io BTC v1 release remains unchanged by this registry.
