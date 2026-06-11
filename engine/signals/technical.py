# engine/signals/technical.py
"""Technical analysis engine.

Input: OHLCV DataFrame. Output:
    {
      "score":    float 0-1,          # blended technical score
      "patterns": List[str],          # detector names that fired (strength >= 0.30)
      "strengths": Dict[str, float],  # per-detector strength 0-1 (fired only)
      "detail":   Dict[str, float],   # sub-scores: setup / trend / momentum / volume
      "snapshot": Dict[str, float],   # point-in-time indicator readings for the UI
    }

Each detector is a pure function (Ctx) -> strength 0-1, registered in
_DETECTORS. Structural detectors gate hard (return 0.0 unless the shape is
genuinely present), so strength reflects pattern quality, not leniency.
"""
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional
import math
import pandas as pd

from engine.signals.indicators import (
    sma, rsi, macd, atr, adx, obv, roc, bollinger, bollinger_bandwidth,
    slope, recent_high, recent_low, stochastic_k,
)


# =============================================================================
# Shared per-symbol context: compute every indicator once, let detectors read it
# =============================================================================

@dataclass
class Ctx:
    close: pd.Series
    high: pd.Series
    low: pd.Series
    volume: pd.Series
    sma20: pd.Series
    sma50: pd.Series
    sma200: pd.Series
    rsi14: pd.Series
    macd_line: pd.Series
    macd_signal: pd.Series
    macd_hist: pd.Series
    atr14: pd.Series
    adx14: pd.Series
    obv: pd.Series
    bb_width: pd.Series

    @property
    def now(self) -> float:
        return float(self.close.iloc[-1])

    def last(self, series: pd.Series, default: float = float("nan")) -> float:
        try:
            v = float(series.iloc[-1])
        except (IndexError, TypeError, ValueError):
            return default
        return default if math.isnan(v) else v


def _build_ctx(prices: pd.DataFrame) -> Ctx:
    close = prices["Close"].astype("float64")
    high = prices["High"].astype("float64") if "High" in prices else close
    low = prices["Low"].astype("float64") if "Low" in prices else close
    volume = prices["Volume"].astype("float64") if "Volume" in prices else close * 0.0
    macd_line, macd_sig, macd_hist = macd(close)
    return Ctx(
        close=close, high=high, low=low, volume=volume,
        sma20=sma(close, 20), sma50=sma(close, 50), sma200=sma(close, 200),
        rsi14=rsi(close, 14),
        macd_line=macd_line, macd_signal=macd_sig, macd_hist=macd_hist,
        atr14=atr(high, low, close, 14),
        adx14=adx(high, low, close, 14),
        obv=obv(close, volume),
        bb_width=bollinger_bandwidth(close, 20),
    )


def _clamp(x: float) -> float:
    return float(max(0.0, min(1.0, x)))


# =============================================================================
# Cup-and-handle (structural, hard-gated) — unchanged logic from v1
# =============================================================================

_CUP_MIN_BARS = 70          # need a long enough base to be a real cup
_CUP_WINDOW = 77            # bars examined for the pattern
_CUP_HANDLE_BARS = 12       # trailing bars treated as the handle
_CUP_RIM_BARS = 5           # leading bars defining the left rim
_DEPTH_MIN = 0.12           # cup must be a meaningful pullback...
_DEPTH_MAX = 0.50           # ...but not a crash
_RIM_BALANCE_MIN = 0.90     # left and right rims must be close in height
_BOTTOM_POS_LO = 0.30       # the low must sit in the middle of the cup...
_BOTTOM_POS_HI = 0.70       # ...not at an edge (that's a V or a slide)
_ROUNDNESS_MIN = 0.55       # time spent basing near the low (rounded, not a V)
_HANDLE_DIP_MIN = 0.02      # a real handle pulls back at least a little...
_HANDLE_DIP_MAX = 0.15      # ...but stays shallow
_HANDLE_FLOOR = 0.50        # handle low must stay in the upper half of the base
_PROXIMITY_MIN = 0.96       # price must be within ~4% of the rim (breakout-ready)


def _roundness(cup: pd.Series, cup_bottom: float, left_rim: float) -> float:
    """Fraction of cup bars sitting in the lowest third of its depth."""
    depth = left_rim - cup_bottom
    if depth <= 0 or len(cup) == 0:
        return 0.0
    low_band = cup_bottom + depth / 3.0
    return float((cup <= low_band).sum()) / float(len(cup))


def _detect_cup_and_handle(ctx: "Ctx") -> float:
    """0-1 strength of a cup-and-handle ending near now, else 0. Hard gates:
    base length, sane depth, level rims, centred low, rounded base, real but
    shallow handle, and breakout-ready proximity to the rim."""
    close = ctx.close
    n = len(close)
    if n < _CUP_MIN_BARS:
        return 0.0
    vals = close.iloc[-_CUP_WINDOW:].reset_index(drop=True)
    w = len(vals)
    cup_end = w - _CUP_HANDLE_BARS
    if cup_end <= _CUP_RIM_BARS:
        return 0.0

    left_rim = float(vals.iloc[:_CUP_RIM_BARS].max())
    cup = vals.iloc[_CUP_RIM_BARS:cup_end]
    handle = vals.iloc[cup_end:]
    if len(cup) == 0 or left_rim <= 0:
        return 0.0

    cup_bottom = float(cup.min())
    bottom_idx = int(cup.idxmin())
    right_rim = float(handle.max())
    now = float(vals.iloc[-1])

    depth = (left_rim - cup_bottom) / left_rim
    if depth < _DEPTH_MIN or depth > _DEPTH_MAX:
        return 0.0

    rim_balance = 1.0 - min(1.0, abs(left_rim - right_rim) / left_rim)
    if rim_balance < _RIM_BALANCE_MIN:
        return 0.0

    pos = (bottom_idx - _CUP_RIM_BARS) / max(1, (cup_end - _CUP_RIM_BARS))
    if pos < _BOTTOM_POS_LO or pos > _BOTTOM_POS_HI:
        return 0.0

    roundness = _roundness(cup, cup_bottom, left_rim)
    if roundness < _ROUNDNESS_MIN:
        return 0.0

    handle_low = float(handle.min())
    handle_dip = (right_rim - handle_low) / right_rim if right_rim else 1.0
    if handle_dip < _HANDLE_DIP_MIN or handle_dip > _HANDLE_DIP_MAX:
        return 0.0
    handle_floor_level = cup_bottom + _HANDLE_FLOOR * (left_rim - cup_bottom)
    if handle_low < handle_floor_level:
        return 0.0

    proximity = 1.0 - min(1.0, abs(right_rim - now) / right_rim)
    if proximity < _PROXIMITY_MIN:
        return 0.0

    score = (0.30 * rim_balance + 0.30 * roundness + 0.25 * proximity
             + 0.15 * (1.0 - handle_dip / _HANDLE_DIP_MAX))
    return _clamp(score)


# =============================================================================
# Breakout / trend / momentum detectors
# =============================================================================

def _detect_breakout(ctx: Ctx) -> float:
    """Price clears 60-bar resistance on >=1.5x average volume."""
    close, volume = ctx.close, ctx.volume
    if len(close) < 30:
        return 0.0
    resistance = recent_high(close, lookback=60, exclude_last=1)
    if ctx.now <= resistance:
        return 0.0
    avg_vol = float(volume.iloc[-21:-1].mean())
    if avg_vol <= 0:
        return 0.0
    vol_ratio = float(volume.iloc[-1]) / avg_vol
    if vol_ratio < 1.5:
        return 0.0
    return _clamp((vol_ratio - 1.5) / 1.5)


def _detect_uptrend(ctx: Ctx) -> float:
    """Price above rising 50- and 200-day SMAs."""
    if len(ctx.close) < 200:
        return 0.0
    sma50, sma200 = ctx.sma50, ctx.sma200
    rising50 = sma50.iloc[-1] > sma50.iloc[-10]
    rising200 = sma200.iloc[-1] > sma200.iloc[-20]
    above = ctx.now > sma50.iloc[-1] > sma200.iloc[-1]
    if above and rising50 and rising200:
        return 1.0
    if above and rising50:
        return 0.5
    return 0.0


def _detect_golden_cross(ctx: Ctx) -> float:
    """SMA50 crossed above SMA200 within the last 15 bars; fresher = stronger."""
    if len(ctx.close) < 215:
        return 0.0
    diff = (ctx.sma50 - ctx.sma200).dropna()
    if len(diff) < 16 or diff.iloc[-1] <= 0:
        return 0.0
    window = diff.iloc[-16:].reset_index(drop=True)
    crossed = (window.shift(1) <= 0) & (window > 0)
    if not bool(crossed.any()):
        return 0.0
    bars_ago = (len(window) - 1) - int(crossed[crossed].index[-1])
    freshness = 1.0 - bars_ago / 15.0
    # confirm with a rising 200-day to avoid whipsaw crosses in chop
    rising200 = ctx.sma200.iloc[-1] >= ctx.sma200.iloc[-10]
    return _clamp(freshness * (1.0 if rising200 else 0.6))


def _detect_pullback_to_trend(ctx: Ctx) -> float:
    """Quality dip: established uptrend, price pulls back to the 50-day and holds.

    Gates: above 200-SMA with a rising 50-SMA, a touch of (or close approach
    to) the 50-SMA within the last 5 bars, RSI in the 35-60 reset zone, and
    the last close ticking back up.
    """
    if len(ctx.close) < 210:
        return 0.0
    close, sma50, sma200 = ctx.close, ctx.sma50, ctx.sma200
    if math.isnan(sma50.iloc[-1]) or math.isnan(sma200.iloc[-1]):
        return 0.0
    if ctx.now <= float(sma200.iloc[-1]):
        return 0.0
    if sma50.iloc[-1] <= sma50.iloc[-15]:
        return 0.0
    # touched (or came within 1.5% of) the 50-day within the last 5 bars
    recent = close.iloc[-5:]
    ma_recent = sma50.iloc[-5:]
    near = ((recent - ma_recent).abs() / ma_recent <= 0.015) | (recent < ma_recent)
    if not bool(near.any()):
        return 0.0
    r = ctx.last(ctx.rsi14, 50.0)
    if not (35.0 <= r <= 60.0):
        return 0.0
    if float(close.iloc[-1]) <= float(close.iloc[-2]):
        return 0.0
    # strength: tighter pullback + RSI reset depth
    dist = abs(ctx.now - float(sma50.iloc[-1])) / float(sma50.iloc[-1])
    tightness = 1.0 - min(1.0, dist / 0.05)
    reset = 1.0 - abs(r - 45.0) / 25.0
    return _clamp(0.6 * tightness + 0.4 * reset)


def _detect_bull_flag(ctx: Ctx) -> float:
    """Sharp pole (>=15% in ~20 bars) then a tight, drifting consolidation.

    The flag must hold the upper half of the pole, stay tight (range < 50%
    of the pole height), and volume should dry up versus the pole's volume.
    """
    close, volume = ctx.close, ctx.volume
    if len(close) < 45:
        return 0.0
    flag_len = 10
    flag = close.iloc[-flag_len:]
    pole = close.iloc[-(flag_len + 20):-flag_len]
    if len(pole) < 15:
        return 0.0
    pole_start = float(pole.iloc[0])
    pole_top = float(pole.max())
    if pole_start <= 0:
        return 0.0
    pole_gain = (pole_top - pole_start) / pole_start
    if pole_gain < 0.15:
        return 0.0
    flag_high, flag_low = float(flag.max()), float(flag.min())
    pole_height = pole_top - pole_start
    if pole_height <= 0:
        return 0.0
    flag_range = (flag_high - flag_low) / pole_height
    if flag_range > 0.50:
        return 0.0
    # flag floor must hold the upper half of the pole
    if flag_low < pole_start + 0.5 * pole_height:
        return 0.0
    # volume contraction during the flag
    pole_vol = float(volume.iloc[-(flag_len + 20):-flag_len].mean())
    flag_vol = float(volume.iloc[-flag_len:].mean())
    vol_dry = 1.0 if pole_vol <= 0 else _clamp(1.5 - flag_vol / pole_vol)
    tightness = 1.0 - flag_range / 0.50
    return _clamp(0.45 * min(1.0, pole_gain / 0.30) + 0.35 * tightness + 0.20 * vol_dry)


def _detect_double_bottom(ctx: Ctx) -> float:
    """Two distinct lows within 3% of each other, a >=8% bounce between them,
    and price now recovering toward the neckline."""
    close = ctx.close
    if len(close) < 90:
        return 0.0
    window = close.iloc[-90:].reset_index(drop=True)
    first_half = window.iloc[:45]
    second_half = window.iloc[45:]
    low1, idx1 = float(first_half.min()), int(first_half.idxmin())
    low2, idx2 = float(second_half.min()), int(second_half.idxmin())
    if low1 <= 0 or idx2 - idx1 < 15:
        return 0.0
    if abs(low1 - low2) / low1 > 0.03:
        return 0.0
    between = window.iloc[idx1:idx2 + 1]
    peak = float(between.max())
    bounce = (peak - max(low1, low2)) / max(low1, low2)
    if bounce < 0.08:
        return 0.0
    # second low must be recent enough to matter and price recovering
    if idx2 < len(window) - 40:
        return 0.0
    now = float(window.iloc[-1])
    progress = (now - low2) / (peak - low2) if peak > low2 else 0.0
    if progress < 0.5:
        return 0.0
    match_q = 1.0 - (abs(low1 - low2) / low1) / 0.03
    return _clamp(0.4 * match_q + 0.6 * min(1.0, progress))


def _detect_bollinger_squeeze(ctx: Ctx) -> float:
    """Volatility coil: 20-day band width in its tightest decile of the last
    120 bars, with price holding the upper half of the bands."""
    bw = ctx.bb_width.dropna()
    if len(bw) < 120:
        return 0.0
    hist = bw.iloc[-120:]
    current = float(hist.iloc[-1])
    pctile = float((hist <= current).sum()) / len(hist)
    if pctile > 0.10:
        return 0.0
    mid, upper, _lower = bollinger(ctx.close, 20)
    m, u = float(mid.iloc[-1]), float(upper.iloc[-1])
    if math.isnan(m) or ctx.now < m:
        return 0.0
    position = (ctx.now - m) / (u - m) if u > m else 0.0
    return _clamp(0.6 * (1.0 - pctile / 0.10) + 0.4 * _clamp(position))


def _detect_obv_accumulation(ctx: Ctx) -> float:
    """Volume leads price: OBV rising decisively over 30 bars while price has
    not yet moved as much (institutional accumulation footprint)."""
    if len(ctx.close) < 60:
        return 0.0
    # shift OBV positive so the normalized slope is stable regardless of sign
    obv_slope = slope(ctx.obv - ctx.obv.min() + 1.0, 30)
    price_slope = slope(ctx.close, 30)
    if obv_slope <= 0.002:
        return 0.0
    if price_slope < -0.001:   # falling price + rising OBV is a divergence, not entry
        return 0.0
    edge = obv_slope - max(0.0, price_slope)
    if edge <= 0:
        return 0.0
    return _clamp(edge / 0.01)


def _detect_high_52w_momentum(ctx: Ctx) -> float:
    """Leadership: within 5% of the 52-week high, positive 3-month return,
    and a trending ADX. New highs tend to beget new highs."""
    close = ctx.close
    if len(close) < 200:
        return 0.0
    hi = recent_high(close, lookback=min(len(close), 252))
    if hi <= 0:
        return 0.0
    dist = (hi - ctx.now) / hi
    if dist > 0.05:
        return 0.0
    r3m = float(roc(close, 63).iloc[-1]) if len(close) > 63 else 0.0
    if math.isnan(r3m) or r3m <= 0:
        return 0.0
    a = ctx.last(ctx.adx14, 0.0)
    if a < 20.0:
        return 0.0
    closeness = 1.0 - dist / 0.05
    trendiness = _clamp((a - 20.0) / 20.0)
    return _clamp(0.5 * closeness + 0.3 * min(1.0, r3m / 0.25) + 0.2 * trendiness)


def _detect_macd_bull_cross(ctx: Ctx) -> float:
    """MACD line crossed above its signal within the last 5 bars, confirmed by
    an up-day. Crosses from below the zero line (early reversal) score higher."""
    diff = (ctx.macd_line - ctx.macd_signal).dropna()
    if len(diff) < 6 or diff.iloc[-1] <= 0:
        return 0.0
    window = diff.iloc[-6:]
    crossed = (window.shift(1) <= 0) & (window > 0)
    if not bool(crossed.any()):
        return 0.0
    if float(ctx.close.iloc[-1]) <= float(ctx.close.iloc[-2]):
        return 0.0
    level = float(ctx.macd_line.iloc[-1])
    price = ctx.now if ctx.now > 0 else 1.0
    norm_level = level / price
    early = 1.0 if norm_level < 0 else _clamp(1.0 - norm_level / 0.03)
    return _clamp(0.5 + 0.5 * early)


def _detect_oversold_reversal(ctx: Ctx) -> float:
    """Washed-out dip in a long-term uptrend turning back up: RSI dipped below
    35 within the last 5 bars, has hooked up, and price holds the 200-day."""
    if len(ctx.close) < 210:
        return 0.0
    s200 = float(ctx.sma200.iloc[-1])
    if math.isnan(s200) or ctx.now < s200:
        return 0.0
    r = ctx.rsi14.dropna()
    if len(r) < 6:
        return 0.0
    recent = r.iloc[-6:]
    dipped = float(recent.min())
    if dipped > 35.0:
        return 0.0
    if float(r.iloc[-1]) <= dipped + 2.0:   # must be hooking up off the low
        return 0.0
    if float(ctx.close.iloc[-1]) <= float(ctx.close.iloc[-2]):
        return 0.0
    depth = _clamp((35.0 - dipped) / 15.0)          # deeper washout = bigger snap
    recovery = _clamp((float(r.iloc[-1]) - dipped) / 15.0)
    return _clamp(0.4 + 0.3 * depth + 0.3 * recovery)


# =============================================================================
# Registry + sub-score composition
# =============================================================================

_DETECTORS: Dict[str, Callable[[Ctx], float]] = {
    "cup_and_handle": _detect_cup_and_handle,
    "breakout": _detect_breakout,
    "uptrend": _detect_uptrend,
    "golden_cross": _detect_golden_cross,
    "pullback_to_trend": _detect_pullback_to_trend,
    "bull_flag": _detect_bull_flag,
    "double_bottom": _detect_double_bottom,
    "bollinger_squeeze": _detect_bollinger_squeeze,
    "obv_accumulation": _detect_obv_accumulation,
    "high_52w_momentum": _detect_high_52w_momentum,
    "macd_bull_cross": _detect_macd_bull_cross,
    "oversold_reversal": _detect_oversold_reversal,
}

# Detector classes:
# - `uptrend` describes the backdrop; it feeds the trend sub-score only.
# - PRIMARY detectors are structural entries that can carry a pick.
# - SECONDARY detectors (MACD cross, OBV accumulation) fire often; they
#   confirm a primary setup but cannot headline one on their own.
_SECONDARY_DETECTORS = ("macd_bull_cross", "obv_accumulation")
_PRIMARY_DETECTORS = [k for k in _DETECTORS
                      if k != "uptrend" and k not in _SECONDARY_DETECTORS]

_PATTERN_MIN = 0.30     # a detector must reach this strength to be a "pattern"
_SECONDARY_CAP = 0.35   # max setup score when only secondary signals fired


def _setup_score(strengths: Dict[str, float]) -> float:
    """Best primary setup carries the score; confirmations add a little."""
    primary = sorted((strengths.get(k, 0.0) for k in _PRIMARY_DETECTORS), reverse=True)
    secondary = sorted((strengths.get(k, 0.0) for k in _SECONDARY_DETECTORS), reverse=True)
    score = primary[0] if primary else 0.0
    if len(primary) > 1:
        score += 0.25 * primary[1]
    if len(primary) > 2:
        score += 0.10 * primary[2]
    if secondary:
        score += 0.10 * secondary[0]
    if len(secondary) > 1:
        score += 0.05 * secondary[1]
    if not primary or primary[0] == 0.0:
        score = min(score, _SECONDARY_CAP)
    return _clamp(score)


def _trend_score(ctx: Ctx, strengths: Dict[str, float]) -> float:
    parts: List[float] = [strengths.get("uptrend", 0.0)]
    a = ctx.last(ctx.adx14, float("nan"))
    if not math.isnan(a):
        parts.append(_clamp((a - 15.0) / 25.0))     # ADX 15->40 maps to 0->1
    s50 = ctx.last(ctx.sma50, float("nan"))
    if not math.isnan(s50) and s50 > 0:
        # holding above the 50-day is healthy; deeply below it is broken
        d = (ctx.now - s50) / s50
        parts.append(_clamp(0.5 + max(-0.15, min(d, 0.15)) / 0.15 * 0.5))
    return _clamp(sum(parts) / len(parts)) if parts else 0.0


def _momentum_score(ctx: Ctx) -> float:
    r = ctx.last(ctx.rsi14, float("nan"))
    if math.isnan(r):
        rsi_part = 0.5
    elif 50.0 < r <= 70.0:
        rsi_part = 1.0
    elif 40.0 <= r <= 50.0:
        rsi_part = 0.5
    elif r > 70.0:
        rsi_part = 0.3        # overbought: caution, not a green light
    else:
        rsi_part = 0.0
    hist = ctx.last(ctx.macd_hist, 0.0)
    hist_prev = float(ctx.macd_hist.iloc[-2]) if len(ctx.macd_hist) > 1 else 0.0
    if math.isnan(hist_prev):
        hist_prev = 0.0
    macd_part = 1.0 if (hist > 0 and hist >= hist_prev) else (0.6 if hist > 0 else 0.0)
    r1m = float(roc(ctx.close, 21).iloc[-1]) if len(ctx.close) > 21 else float("nan")
    roc_part = 0.5 if math.isnan(r1m) else _clamp(0.5 + r1m / 0.10 * 0.5)
    return _clamp(0.4 * rsi_part + 0.35 * macd_part + 0.25 * roc_part)


def _volume_score(ctx: Ctx) -> float:
    vol = ctx.volume
    if len(vol) < 25 or float(vol.iloc[-21:-1].mean()) <= 0:
        return 0.5
    ratio = float(vol.iloc[-5:].mean()) / float(vol.iloc[-21:-1].mean())
    ratio_part = _clamp((ratio - 0.7) / 0.8)        # 0.7x -> 0, 1.5x -> 1
    obv_part = _clamp(0.5 + slope(ctx.obv - ctx.obv.min() + 1.0, 30) / 0.01 * 0.5)
    return _clamp(0.5 * ratio_part + 0.5 * obv_part)


# =============================================================================
# Snapshot for the UI
# =============================================================================

def _round(x, nd: int = 4) -> Optional[float]:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), nd)


def build_snapshot(ctx: Ctx) -> Dict[str, Optional[float]]:
    """Point-in-time indicator readings surfaced on the dashboard."""
    close = ctx.close
    n = len(close)
    price = ctx.now
    hi52 = recent_high(close, lookback=min(n, 252)) if n else float("nan")
    lo52 = recent_low(close, lookback=min(n, 252)) if n else float("nan")
    atr_v = ctx.last(ctx.atr14, float("nan"))
    vol_ratio = float("nan")
    if n >= 25:
        base = float(ctx.volume.iloc[-21:-1].mean())
        if base > 0:
            vol_ratio = float(ctx.volume.iloc[-1]) / base
    stoch = stochastic_k(ctx.high, ctx.low, close)

    def _dist(ref: float) -> float:
        return (price / ref - 1.0) if (ref and not math.isnan(ref) and ref > 0) else float("nan")

    return {
        "rsi14": _round(ctx.last(ctx.rsi14, float("nan")), 1),
        "macd_hist": _round(ctx.last(ctx.macd_hist, float("nan")) / price if price else float("nan"), 5),
        "adx14": _round(ctx.last(ctx.adx14, float("nan")), 1),
        "stoch_k": _round(stoch.iloc[-1] if len(stoch.dropna()) else float("nan"), 1),
        "atr_pct": _round(atr_v / price if price else float("nan"), 4),
        "sma50_dist": _round(_dist(ctx.last(ctx.sma50, float("nan")))),
        "sma200_dist": _round(_dist(ctx.last(ctx.sma200, float("nan")))),
        "high_52w_dist": _round(_dist(hi52)),
        "low_52w_dist": _round(_dist(lo52)),
        "vol_ratio": _round(vol_ratio, 2),
        "ret_1m": _round(float(roc(close, 21).iloc[-1]) if n > 21 else float("nan")),
        "ret_3m": _round(float(roc(close, 63).iloc[-1]) if n > 63 else float("nan")),
        "ret_6m": _round(float(roc(close, 126).iloc[-1]) if n > 126 else float("nan")),
    }


# =============================================================================
# Public entry point
# =============================================================================

def scan_technical(prices: pd.DataFrame) -> Dict[str, object]:
    """Run all detectors and compose the technical score."""
    if prices is None or len(prices) == 0:
        return {"score": 0.0, "patterns": [], "strengths": {},
                "detail": {}, "snapshot": {}}
    ctx = _build_ctx(prices)

    strengths: Dict[str, float] = {}
    for name, fn in _DETECTORS.items():
        try:
            s = float(fn(ctx))
        except Exception:
            s = 0.0
        if s > 0.0:
            strengths[name] = round(s, 4)

    setup = _setup_score(strengths)
    trend = _trend_score(ctx, strengths)
    momentum = _momentum_score(ctx)
    volume = _volume_score(ctx)

    # No detector fired at all -> no signal. Trend/momentum/volume modulate a
    # signal; neutral baseline readings alone must not manufacture a score.
    if not strengths:
        score = 0.0
    else:
        score = _clamp(0.45 * setup + 0.25 * trend + 0.18 * momentum + 0.12 * volume)

    fired = {k: v for k, v in strengths.items() if v >= _PATTERN_MIN}
    patterns = sorted(fired, key=lambda k: fired[k], reverse=True)

    return {
        "score": float(score),
        "patterns": patterns,
        "strengths": fired,
        "detail": {
            "setup": round(setup, 4),
            "trend": round(trend, 4),
            "momentum": round(momentum, 4),
            "volume": round(volume, 4),
        },
        "snapshot": build_snapshot(ctx),
    }
