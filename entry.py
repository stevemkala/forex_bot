# entry.py
import pandas as pd

def is_engulfing(prev, curr) -> str | None:
    """
    Detect bullish or bearish engulfing candle.
    Returns 'bullish', 'bearish', or None.
    """
    prev_body = abs(prev["close"] - prev["open"])
    curr_body = abs(curr["close"] - curr["open"])

    bullish = (
        prev["close"] < prev["open"] and   # prev bearish
        curr["close"] > curr["open"] and   # curr bullish
        curr["open"]  < prev["close"] and  # opens below prev close
        curr["close"] > prev["open"]       # closes above prev open
    )
    bearish = (
        prev["close"] > prev["open"] and
        curr["close"] < curr["open"] and
        curr["open"]  > prev["close"] and
        curr["close"] < prev["open"]
    )
    if bullish and curr_body > prev_body:
        return "bullish"
    if bearish and curr_body > prev_body:
        return "bearish"
    return None


def is_pin_bar(candle, threshold: float = 2.0) -> str | None:
    """
    Detect bullish or bearish pin bar (hammer / shooting star).
    Returns 'bullish', 'bearish', or None.
    """
    body   = abs(candle["close"] - candle["open"])
    rng    = candle["high"] - candle["low"]
    upper  = candle["high"] - max(candle["open"], candle["close"])
    lower  = min(candle["open"], candle["close"]) - candle["low"]

    if rng == 0:
        return None

    # Bullish pin bar: long lower wick
    if lower > threshold * body and lower > upper:
        return "bullish"
    # Bearish pin bar: long upper wick
    if upper > threshold * body and upper > lower:
        return "bearish"
    return None


def check_entry_signal(df: pd.DataFrame, zones: list[dict]) -> list[dict]:
    """
    Check the last 2 closed candles for confirmation signals at fresh zones.
    Returns a list of trade signals ready for execution.
    """
    signals = []
    prev   = df.iloc[-2]
    curr   = df.iloc[-1]

    for zone in zones:
        # ── Check if current price is inside or just touched the zone ──
        price_in_zone = (
            curr["low"]  <= zone["top"] and
            curr["high"] >= zone["bottom"]
        )
        if not price_in_zone:
            continue

        # ── Demand zone → look for bullish confirmation ──
        if zone["type"] == "demand":
            engulf  = is_engulfing(prev, curr)
            pin     = is_pin_bar(curr)
            if engulf == "bullish" or pin == "bullish":
                signals.append({
                    "action":      "buy",
                    "zone":        zone,
                    "signal_type": engulf or pin,
                    "entry_price": curr["close"],
                    "sl_price":    zone["bottom"],   # SL below zone
                })

        # ── Supply zone → look for bearish confirmation ──
        elif zone["type"] == "supply":
            engulf  = is_engulfing(prev, curr)
            pin     = is_pin_bar(curr)
            if engulf == "bearish" or pin == "bearish":
                signals.append({
                    "action":      "sell",
                    "zone":        zone,
                    "signal_type": engulf or pin,
                    "entry_price": curr["close"],
                    "sl_price":    zone["top"],      # SL above zone
                })

    return signals