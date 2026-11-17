"""Independent formula-parity checks; deliberately does not import engine helpers."""
import math
from statistics import fmean
import pytest
from forward.universal_indicator_engine_v1 import OHLCVBar, calculate_indicators, build_snapshot


def fixture(n=280):
    out=[]
    prev=100.0
    for i in range(n):
        close=100 + 0.035*i + 2.7*math.sin(i*.17) + .8*math.sin(i*.037)
        op=prev
        hi=max(op,close)+.35+(i%5)*.025
        lo=min(op,close)-.30-(i%7)*.02
        vol=80+(i%13)*4+abs(math.sin(i*.11))*35
        out.append(OHLCVBar(1_700_000_000+i*60,op,hi,lo,close,vol,vol*close,True))
        prev=close
    return out


def ref_ema(values, n):
    if len(values)<n:return None
    value=sum(values[:n])/n
    alpha=2/(n+1)
    for x in values[n:]:value=alpha*x+(1-alpha)*value
    return value


def ref_rsi(values,n):
    diffs=[values[i]-values[i-1] for i in range(1,len(values))]
    gains=[max(x,0) for x in diffs];losses=[max(-x,0) for x in diffs]
    if len(gains)<n:return None
    ag=sum(gains[:n])/n;al=sum(losses[:n])/n
    for g,l in zip(gains[n:],losses[n:]):
        ag=((n-1)*ag+g)/n;al=((n-1)*al+l)/n
    if al==0:return 100.0 if ag else 50.0
    return 100-100/(1+ag/al)


def ref_true_ranges(bars):
    return [max(b.high-b.low,abs(b.high-bars[i-1].close),abs(b.low-bars[i-1].close))
            for i,b in enumerate(bars) if i]


def ref_wilder_sum(xs,n):
    if len(xs)<n:return []
    out=[None]*(n-1);v=sum(xs[:n]);out.append(v)
    for x in xs[n:]:
        v=v-v/n+x;out.append(v)
    return out


def ref_dmi(bars,n):
    tr=ref_true_ranges(bars);plus=[];minus=[]
    for i in range(1,len(bars)):
        up=bars[i].high-bars[i-1].high
        down=bars[i-1].low-bars[i].low
        plus.append(up if up>down and up>0 else 0.)
        minus.append(down if down>up and down>0 else 0.)
    atr=ref_wilder_sum(tr,n);p=ref_wilder_sum(plus,n);m=ref_wilder_sum(minus,n)
    dx=[]
    for a,x,y in zip(atr,p,m):
        if a is not None and a:
            pi,mi=100*x/a,100*y/a
            dx.append(100*abs(pi-mi)/(pi+mi) if pi+mi else 0.)
    adx_series=ref_wilder_sum(dx,n)
    last_atr=atr[-1]/n
    return last_atr,100*p[-1]/atr[-1],100*m[-1]/atr[-1],adx_series[-1]/n


def test_independent_reference_parity_for_core_indicators():
    bars=fixture();c=[b.close for b in bars];h=[b.high for b in bars];l=[b.low for b in bars]
    out=calculate_indicators(bars,volume_semantics_qualified=True)
    close=c[-1]
    assert out["ema_20"].value==pytest.approx(ref_ema(c,20),rel=1e-12)
    assert out["ema_50"].value==pytest.approx(ref_ema(c,50),rel=1e-12)
    assert out["ema_200"].value==pytest.approx(ref_ema(c,200),rel=1e-12)
    assert out["rsi_14"].value==pytest.approx(ref_rsi(c,14),rel=1e-12)
    atr,pdi,mdi,adx=ref_dmi(bars,14)
    assert out["atr_14"].value==pytest.approx(atr,rel=1e-12)
    assert out["atr_pct"].value==pytest.approx(100*atr/close,rel=1e-12)
    assert out["plus_di_14"].value==pytest.approx(pdi,rel=1e-12)
    assert out["minus_di_14"].value==pytest.approx(mdi,rel=1e-12)
    assert out["adx_14"].value==pytest.approx(adx,rel=1e-12)
    n=20;window=c[-n:];mid=fmean(window)
    sd=math.sqrt(sum((x-mid)**2 for x in window)/n)
    assert out["bollinger_mid"].value==pytest.approx(mid,rel=1e-12)
    assert out["bollinger_upper"].value==pytest.approx(mid+2*sd,rel=1e-12)
    assert out["bollinger_lower"].value==pytest.approx(mid-2*sd,rel=1e-12)
    assert out["donchian_upper_prior"].value==pytest.approx(max(h[-21:-1]),rel=1e-12)
    assert out["donchian_lower_prior"].value==pytest.approx(min(l[-21:-1]),rel=1e-12)
    assert out["roc_10_pct"].value==pytest.approx(100*(c[-1]/c[-11]-1),rel=1e-12)
    hh=max(h[-14:]);ll=min(l[-14:])
    assert out["williams_r_14"].value==pytest.approx(-100*(hh-close)/(hh-ll),rel=1e-12)
    typical=[(b.high+b.low+b.close)/3 for b in bars[-20:]]
    mean=fmean(typical);mad=fmean(abs(x-mean) for x in typical)
    assert out["cci_20"].value==pytest.approx((typical[-1]-mean)/(.015*mad),rel=1e-12)


def test_vwap_and_flow_reference_parity():
    bars=fixture();out=calculate_indicators(bars,volume_semantics_qualified=True)
    win=bars[-20:]
    assert out["vwap_20"].value==pytest.approx(sum(b.quote_volume for b in win)/sum(b.volume for b in win),rel=1e-12)
    assert out["relative_volume_20"].value==pytest.approx(win[-1].volume/(sum(b.volume for b in bars[-21:-1])/20),rel=1e-12)
    mult=[(2*b.close-b.high-b.low)/(b.high-b.low) for b in win]
    assert out["cmf_20"].value==pytest.approx(sum(m*b.volume for m,b in zip(mult,win))/sum(b.volume for b in win),rel=1e-12)


def test_causal_prefix_is_invariant_to_unseen_future_and_donchian_excludes_current():
    bars=fixture()
    prefix=bars[:250]
    base=calculate_indicators(prefix,volume_semantics_qualified=True)
    # Two alternative future paths are deliberately not passed into the as-of snapshot.
    future_a=[OHLCVBar(prefix[-1].timestamp+60,110,112,108,111,100,11100,True)]
    future_b=[OHLCVBar(prefix[-1].timestamp+60,9000,9500,8500,9200,9999,91990800,True)]
    snap_a=calculate_indicators(prefix,volume_semantics_qualified=True)
    snap_b=calculate_indicators(prefix,volume_semantics_qualified=True)
    for key in ("ema_20","ema_50","ema_200","rsi_14","adx_14","atr_14",
                "bollinger_upper","bollinger_lower","donchian_upper_prior",
                "donchian_lower_prior","vwap_20","cmf_20"):
        assert snap_a[key].value==pytest.approx(snap_b[key].value,rel=1e-12,abs=1e-12),key
    # Current extreme candle must not contaminate its own prior Donchian reference.
    extreme=OHLCVBar(prefix[-1].timestamp+60,110,10000,1,111,100,11100,True)
    after=calculate_indicators(prefix+[extreme],volume_semantics_qualified=True)
    assert after["donchian_upper_prior"].value==pytest.approx(max(b.high for b in prefix[-20:]))
    assert after["donchian_lower_prior"].value==pytest.approx(min(b.low for b in prefix[-20:]))


def test_reference_edge_cases_for_flat_market_are_finite():
    bars=[OHLCVBar(1_700_000_000+i*60,100,101,99,100,10,1000,True) for i in range(260)]
    out=calculate_indicators(bars,volume_semantics_qualified=True)
    assert out["rsi_14"].value==50
    assert out["efficiency_ratio_20"].value==0
    assert out["bollinger_percent_b"].value==.5
    assert out["williams_r_14"].value==-50
    assert all(v.value is None or math.isfinite(v.value) for v in out.values())


def test_market_and_symbol_agnostic_price_math_is_scale_invariant():
    base=fixture(280)
    scaled=[OHLCVBar(b.timestamp,b.open*10,b.high*10,b.low*10,b.close*10,
                     b.volume,b.quote_volume*10,True) for b in base]
    a=build_snapshot(base,venue="gateio",market="spot",symbol="BTC_USDT",timeframe="15m",volume_semantics_qualified=True)
    b=build_snapshot(scaled,venue="generic_provider",market="forex_spot",symbol="EUR_USD",timeframe="1h",volume_semantics_qualified=False)
    assert a.regime.label==b.regime.label
    for key in ("rsi_14","plus_di_14","minus_di_14","adx_14","atr_pct",
                "bollinger_percent_b","bollinger_width_pct","efficiency_ratio_20",
                "choppiness_14"):
        assert a.indicators[key].value==pytest.approx(b.indicators[key].value,rel=1e-10,abs=1e-10),key
    assert b.indicators["ema_20"].value==pytest.approx(a.indicators["ema_20"].value*10,rel=1e-12)
    for key in ("relative_volume_20","mfi_14","cmf_20","vwap_20","obv","obv_change_20"):
        assert b.indicators[key].status == "UNAVAILABLE"
        assert b.indicators[key].reason == "VENUE_VOLUME_UNQUALIFIED"


def test_extended_reference_parity_for_supertrend_choppiness_aroon_stochastic_mfi_obv():
    """Independent scalar references for the remaining nontrivial V1 formulas."""
    bars = fixture(320)
    out = calculate_indicators(bars, volume_semantics_qualified=True)
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    closes = [b.close for b in bars]
    volumes = [b.volume for b in bars]

    # Choppiness: sum of the last 14 true ranges over the last-14-bar range.
    n = 14
    trs = [max(b.high-b.low, abs(b.high-bars[i-1].close), abs(b.low-bars[i-1].close))
           for i, b in enumerate(bars) if i]
    tr_sum = sum(trs[-n:])
    span = max(highs[-n:]) - min(lows[-n:])
    expected_chop = 100 * math.log(tr_sum / span) / math.log(n)
    assert out["choppiness_14"].value == pytest.approx(expected_chop, rel=1e-12)

    # Aroon: bars since the most recent high/low in a 25-bar window.
    n = 25
    wh, wl = highs[-n:], lows[-n:]
    since_high = n - 1 - max(i for i, x in enumerate(wh) if x == max(wh))
    since_low = n - 1 - max(i for i, x in enumerate(wl) if x == min(wl))
    assert out["aroon_up_25"].value == pytest.approx(100 * (n - since_high) / n)
    assert out["aroon_down_25"].value == pytest.approx(100 * (n - since_low) / n)

    # Stochastic fast %K and simple 3-observation smoothing of independently
    # recomputed rolling %K values.
    n = 14
    ks = []
    for end in range(len(bars) - 3, len(bars)):
        hh = max(highs[end-n+1:end+1])
        ll = min(lows[end-n+1:end+1])
        ks.append(100 * (closes[end] - ll) / (hh - ll) if hh > ll else 50.0)
    assert out["stochastic_k"].value == pytest.approx(ks[-1], rel=1e-12)
    assert out["stochastic_d"].value == pytest.approx(sum(ks) / len(ks), rel=1e-12)

    # MFI: signed typical-price money flow, over 14 changes (15 prices).
    typical = [(b.high + b.low + b.close) / 3 for b in bars]
    positive = negative = 0.0
    for i in range(len(bars)-14, len(bars)):
        flow = typical[i] * volumes[i]
        if typical[i] > typical[i-1]:
            positive += flow
        elif typical[i] < typical[i-1]:
            negative += flow
    expected_mfi = 100 - 100 / (1 + positive / negative) if negative else 100.0 if positive else 50.0
    assert out["mfi_14"].value == pytest.approx(expected_mfi, rel=1e-12)

    # OBV is accumulated from the first supplied bar; the 20-bar delta is
    # final OBV minus the OBV immediately before the 20-bar observation span.
    obv_series = [0.0]
    for i in range(1, len(bars)):
        delta = volumes[i] if closes[i] > closes[i-1] else -volumes[i] if closes[i] < closes[i-1] else 0.0
        obv_series.append(obv_series[-1] + delta)
    assert out["obv"].value == pytest.approx(obv_series[-1], rel=1e-12)
    assert out["obv_change_20"].value == pytest.approx(obv_series[-1] - obv_series[-21], rel=1e-12)

    # Independent Wilder ATR + final-band recurrence for Supertrend direction.
    tr_all = [highs[0] - lows[0]] + trs
    atr_sums = ref_wilder_sum(tr_all[1:], 14)
    final_upper = final_lower = None
    direction = None
    for i in range(14, len(bars)):
        atr_value = atr_sums[i-1] / 14 if atr_sums[i-1] is not None else None
        if atr_value is None:
            continue
        midpoint = (highs[i] + lows[i]) / 2
        basic_upper = midpoint + 3.0 * atr_value
        basic_lower = midpoint - 3.0 * atr_value
        if final_upper is None:
            final_upper, final_lower = basic_upper, basic_lower
            direction = 1.0 if closes[i] >= midpoint else -1.0
            continue
        prev_upper, prev_lower = final_upper, final_lower
        final_upper = basic_upper if basic_upper < prev_upper or closes[i-1] > prev_upper else prev_upper
        final_lower = basic_lower if basic_lower > prev_lower or closes[i-1] < prev_lower else prev_lower
        if direction < 0 and closes[i] > final_upper:
            direction = 1.0
        elif direction > 0 and closes[i] < final_lower:
            direction = -1.0
    assert out["supertrend_direction"].value == pytest.approx(direction)


def test_relative_volume_uses_prior_completed_bars_only():
    bars = fixture(260)
    base = calculate_indicators(bars, volume_semantics_qualified=True)
    spike = OHLCVBar(bars[-1].timestamp + 60, bars[-1].close, bars[-1].close + 1,
                     bars[-1].close - 1, bars[-1].close + .1, 10000, 10000*(bars[-1].close+.1), True)
    extended = calculate_indicators(bars + [spike], volume_semantics_qualified=True)
    expected = 10000 / (sum(b.volume for b in bars[-20:]) / 20)
    assert extended["relative_volume_20"].value == pytest.approx(expected, rel=1e-12)
    assert extended["relative_volume_20"].value > base["relative_volume_20"].value
