# data.py
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

# Timeframe map
TIMEFRAMES = {
    "M15": mt5.TIMEFRAME_M15,
    "H1":  mt5.TIMEFRAME_H1,
    "H4":  mt5.TIMEFRAME_H4,
    "D1":  mt5.TIMEFRAME_D1,
}

def get_candles(symbol: str, timeframe: str, n: int = 500) -> pd.DataFrame:
    tf = TIMEFRAMES.get(timeframe)
    if tf is None:
        raise ValueError(f"Invalid timeframe '{timeframe}'. Choose from: {list(TIMEFRAMES.keys())}")

    rates = mt5.copy_rates_from_pos(symbol, tf, 0, n)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"Failed to fetch candles for {symbol} — {mt5.last_error()}")

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df["time"] = df["time"].dt.tz_localize(None)  # ← ADD THIS LINE
    df.set_index("time", inplace=True)
    df = df[["open", "high", "low", "close", "tick_volume"]].rename(
        columns={"tick_volume": "volume"}
    )
    return df.iloc[:-1]


def get_current_price(symbol: str) -> dict:
    """Get the latest bid/ask price for a symbol."""
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise RuntimeError(f"Cannot get tick for {symbol}")
    return {"bid": tick.bid, "ask": tick.ask, "time": datetime.fromtimestamp(tick.time)}