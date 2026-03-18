# strategy.py
import pandas as pd
import numpy as np


# ─── Helpers ────────────────────────────────────────────────────────────────

def candle_body(df: pd.DataFrame) -> list:
    return [abs(c - o) for c, o in zip(df["close"], df["open"])]

def candle_range(df: pd.DataFrame) -> list:
    return [h - l for h, l in zip(df["high"], df["low"])]


# ─── Daily Trend Detection ───────────────────────────────────────────────────

def get_daily_trend(symbol: str) -> str:
    """
    Detect Daily trend.
    Primary: 3 of last 5 Daily candles making new highs/lows
    Fallback: EMA50 vs EMA200 on Daily
    """
    import MetaTrader5 as mt5

    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 30)
    if rates is None or len(rates) < 4:
        print("⚠️  Could not fetch Daily candles")
        return "neutral"

    # Count how many recent candles broke previous high/low
    bullish_breaks = 0
    bearish_breaks = 0

    for i in range(1, min(6, len(rates) - 1)):
        curr_close = rates[i]["close"]
        prev_high  = rates[i + 1]["high"]
        prev_low   = rates[i + 1]["low"]
        if curr_close > prev_high:
            bullish_breaks += 1
        elif curr_close < prev_low:
            bearish_breaks += 1

    if bullish_breaks >= 2:
        print(f"📈 Daily Trend: BULLISH ({bullish_breaks} higher closes)")
        return "bullish"
    elif bearish_breaks >= 2:
        print(f"📉 Daily Trend: BEARISH ({bearish_breaks} lower closes)")
        return "bearish"

    # Fallback: use Daily EMA50 vs EMA200
    closes = [r["close"] for r in reversed(rates)]

    if len(closes) >= 5:
        ema_short = sum(closes[-3:]) / 3
        ema_long  = sum(closes) / len(closes)

        if ema_short > ema_long * 1.0002:
            print(f"📈 Daily Trend: BULLISH (EMA fallback — "
                  f"short {round(ema_short,5)} > long {round(ema_long,5)})")
            return "bullish"
        elif ema_short < ema_long * 0.9998:
            print(f"📉 Daily Trend: BEARISH (EMA fallback — "
                  f"short {round(ema_short,5)} < long {round(ema_long,5)})")
            return "bearish"

    print(f"➡️  Daily Trend: NEUTRAL — no clear direction")
    return "neutral"


# ─── Zone Detection ──────────────────────────────────────────────────────────

def detect_zones(df: pd.DataFrame, impulse_threshold: float = 0.8) -> list[dict]:
    """
    Detect Supply and Demand zones with strict single-candle base rules:

    Base candle rules:
    - Single candle base only (no multi-candle consolidation)
    - Base candle range must be < 50% of the impulse candle range

    Pattern rules:
    - RBR (Rally-Base-Rally)  → Demand continuation zone
    - DBD (Drop-Base-Drop)    → Supply continuation zone
    - RBD (Rally-Base-Drop)   → Supply reversal zone
    - DBR (Drop-Base-Rally)   → Demand reversal zone
    """
    if len(df) < 4:
        return []

    opens  = list(df["open"])
    highs  = list(df["high"])
    lows   = list(df["low"])
    closes = list(df["close"])
    times  = list(df.index.astype(str))

    bodies = [abs(closes[i] - opens[i]) for i in range(len(opens))]
    ranges = [highs[i] - lows[i]        for i in range(len(opens))]

    avg_body = sum(bodies) / len(bodies) if bodies else 0
    if avg_body == 0:
        return []

    zones = []

    for i in range(2, len(df) - 1):
        base_range    = ranges[i - 1]
        impulse_range = ranges[i]
        impulse_body  = bodies[i]

        # ── Rule 1: Single candle base ──
        # Base range must be < 50% of impulse range
        if impulse_range == 0:
            continue
        if base_range >= impulse_range * 0.5:
            continue

        # ── Rule 2: Impulse must be strong ──
        local_slice = bodies[max(0, i - 5):i]
        local_avg   = sum(local_slice) / len(local_slice) if local_slice else 0
        if local_avg == 0:
            continue
        strength = impulse_body / local_avg
        if strength < impulse_threshold:
            continue

        base_high = highs[i - 1]
        base_low  = lows[i - 1]

        # ── Candle before base (i-2) determines pattern type ──
        pre_bullish = closes[i - 2] > opens[i - 2]
        pre_bearish = closes[i - 2] < opens[i - 2]

        # ── Demand Zone — bullish impulse (DBR or RBR) ──
        if closes[i] > opens[i]:
            if pre_bullish:
                pattern = "RBR"   # continuation demand
            else:
                pattern = "DBR"   # reversal demand

            zones.append({
                "type":             "demand",
                "top":              float(base_high),
                "bottom":           float(base_low),
                "formed":           times[i - 1],
                "fresh":            True,
                "pattern":          pattern,
                "impulse_strength": round(float(strength), 2),
                "base_ratio":       round(base_range / impulse_range, 2),
            })

        # ── Supply Zone — bearish impulse (RBD or DBD) ──
        elif closes[i] < opens[i]:
            if pre_bearish:
                pattern = "DBD"   # continuation supply
            else:
                pattern = "RBD"   # reversal supply

            zones.append({
                "type":             "supply",
                "top":              float(base_high),
                "bottom":           float(base_low),
                "formed":           times[i - 1],
                "fresh":            True,
                "pattern":          pattern,
                "impulse_strength": round(float(strength), 2),
                "base_ratio":       round(base_range / impulse_range, 2),
            })

    return zones


# ─── Mark Tested Zones ───────────────────────────────────────────────────────

def mark_tested_zones(zones: list[dict], df: pd.DataFrame) -> list[dict]:
    if not zones or len(df) == 0:
        return zones

    highs = list(df["high"])
    lows  = list(df["low"])
    times = list(df.index.astype(str))

    for zone in zones:
        formed = str(zone["formed"])
        for j in range(len(times)):
            if times[j] <= formed:
                continue
            if lows[j] <= zone["top"] and highs[j] >= zone["bottom"]:
                zone["fresh"] = False
                break

    return zones


# ─── Diagnostics ─────────────────────────────────────────────────────────────

def diagnose_zones(df: pd.DataFrame, symbol: str = "AUDUSD"):
    bodies   = candle_body(df)
    ranges   = candle_range(df)
    avg_body = sum(bodies) / len(bodies) if bodies else 0

    impulses_08 = 0
    impulses_15 = 0
    tight_bases = 0

    for i in range(1, len(df) - 1):
        local = bodies[max(0, i - 5):i]
        avg   = sum(local) / len(local) if local else 0
        if avg == 0:
            continue
        ratio = bodies[i] / avg
        if ratio >= 0.8:
            impulses_08 += 1
        if ratio >= 1.5:
            impulses_15 += 1
        # Count tight bases (range < 50% of next candle)
        if i < len(df) - 1 and ranges[i + 1] > 0:
            if ranges[i] < ranges[i + 1] * 0.5:
                tight_bases += 1

    print(f"""
╔══════════════════════════════════════╗
         🔍 CANDLE DIAGNOSTICS
╠══════════════════════════════════════╣
  Total Candles          : {len(df)}
  Avg Body Size          : {round(avg_body, 5)}
  Max Body Size          : {round(max(bodies), 5)}
  Tight bases (< 50% rng): {tight_bases}
  Impulse candles (≥0.8) : {impulses_08}
  Impulse candles (≥1.5) : {impulses_15}
╚══════════════════════════════════════╝
    """)


# ─── Main ────────────────────────────────────────────────────────────────────

def get_fresh_zones(df: pd.DataFrame, impulse_threshold: float = 0.8) -> list[dict]:
    """Return only fresh untested zones."""
    zones = detect_zones(df, impulse_threshold)
    zones = mark_tested_zones(zones, df)
    fresh = [z for z in zones if z["fresh"]]
    print(f"📦 Found {len(fresh)} fresh zones "
          f"({sum(1 for z in fresh if z['type'] == 'demand')} demand, "
          f"{sum(1 for z in fresh if z['type'] == 'supply')} supply)")
    return fresh