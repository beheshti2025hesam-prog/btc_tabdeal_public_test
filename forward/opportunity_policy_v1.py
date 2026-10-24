from __future__ import annotations
from .opportunity_detector_v1 import OpportunityCandidate

class OpportunityPolicyV1:
    def evaluate(self, *, observed_at, symbol, timeframe, regime, structure_labels=(), structure_events=()):
        labels=tuple(structure_labels); events=tuple(structure_events)
        if symbol!='BTCUSDT' or timeframe!='15m':
            return OpportunityCandidate(observed_at,symbol,timeframe,'NO_CANDIDATE',regime,labels,events,('SCOPE_MISMATCH',))
        if regime not in ('UPTREND','DOWNTREND'):
            return OpportunityCandidate(observed_at,symbol,timeframe,'NO_CANDIDATE',regime,labels,events,('REGIME_NOT_DIRECTIONAL',))
        if not events:
            return OpportunityCandidate(observed_at,symbol,timeframe,'NO_CANDIDATE',regime,labels,events,('NO_STRUCTURE_EVENT',))
        latest=events[-1]
        if regime=='UPTREND' and 'HH' in labels and 'HL' in labels and latest in ('BOS','CHOCH','HH','HL'):
            return OpportunityCandidate(observed_at,symbol,timeframe,'CANDIDATE_LONG',regime,labels,events,('DIRECTIONAL_STRUCTURE_PRESENT',))
        if regime=='DOWNTREND' and 'LL' in labels and 'LH' in labels and latest in ('BOS','CHOCH','LL','LH'):
            return OpportunityCandidate(observed_at,symbol,timeframe,'CANDIDATE_SHORT',regime,labels,events,('DIRECTIONAL_STRUCTURE_PRESENT',))
        return OpportunityCandidate(observed_at,symbol,timeframe,'NO_CANDIDATE',regime,labels,events,('EVENT_DIRECTION_NOT_TRACEABLE',))
