# backtest.py
from mt5_connect import connect, disconnect
from data import get_candles
from strategy import detect_zones, diagnose_zones, get_daily_trend
from risk import calculate_levels
import datetime

# ─── Configuration ────────────────────────────────────────────────────────────

SYMBOL         = "AUDUSD"
TIMEFRAME      = "M15"
HTF            = "H1"
CANDLES        = 50000
RISK_PERCENT   = 1.0
RR_RATIO       = 3.0
MIN_SL_PIPS    = 1
MAX_SL_PIPS    = 20
EMA_PERIOD     = 50
MIN_ZONE_PIPS  = 5
MIN_IMPULSE    = 0.8
ATR_PERIOD     = 14
ATR_MULTIPLIER = 1.5
LOGIN          = 335705
PASSWORD       = "Av3ng3r$"
SERVER         = "EGMSecurities-Demo"

SESSIONS = [
    #("Asian",    2,  5),
    ("London",   8, 12),
    ("New York", 13, 17),
]


# ─── Session Filter ───────────────────────────────────────────────────────────

def is_in_session(time_str: str) -> tuple:
    try:
        dt   = datetime.datetime.strptime(str(time_str)[:19], "%Y-%m-%d %H:%M:%S")
        hour = dt.hour
        for name, start, end in SESSIONS:
            if start <= hour < end:
                return True, name
        return False, None
    except Exception:
        return True, "Unknown"


# ─── ATR Calculator ───────────────────────────────────────────────────────────

def calculate_atr(highs: list, lows: list, closes: list,
                  period: int = 14) -> list:
    trs = [highs[0] - lows[0]]
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i]  - closes[i - 1]),
        )
        trs.append(tr)

    atrs    = [None] * period
    atr_val = sum(trs[:period]) / period
    atrs.append(atr_val)

    for i in range(period + 1, len(trs)):
        atr_val = (atr_val * (period - 1) + trs[i]) / period
        atrs.append(atr_val)

    return atrs


# ─── Ranging Market Detection ─────────────────────────────────────────────────

def is_ranging(symbol: str, lookback: int = 20) -> bool:
    df     = get_candles(symbol, "D1", lookback + 5)
    highs  = list(df["high"])
    lows   = list(df["low"])
    closes = list(df["close"])

    if len(closes) < lookback:
        return False

    recent_highs = highs[-lookback:-1]
    recent_lows  = lows[-lookback:-1]
    last_close   = closes[-1]
    highest_high = max(recent_highs)
    lowest_low   = min(recent_lows)
    total_range  = highest_high - lowest_low

    daily_ranges = [highs[i] - lows[i] for i in range(-lookback, -1)]
    avg_range    = sum(daily_ranges) / len(daily_ranges) if daily_ranges else 0

    is_tight    = total_range < avg_range * 1.5
    no_new_high = last_close < highest_high * 0.998
    no_new_low  = last_close > lowest_low  * 1.002
    ranging     = is_tight and no_new_high and no_new_low

    if ranging:
        print(f"↔️  Market is RANGING — no trades "
              f"(range: {round(total_range/0.0001,1)} pips, "
              f"avg daily: {round(avg_range/0.0001,1)} pips)")
    else:
        print(f"✅ Market is TRENDING — trades allowed")

    return ranging


# ─── Dynamic Trend At Time Of Candle ─────────────────────────────────────────

def get_trend_at_time(daily_highs: list, daily_lows: list,
                      daily_closes: list, daily_times: list,
                      candle_time: str) -> str:
    """
    Get the trend that was active at the time a specific M15 candle formed.
    Uses the daily data that was available up to that point in time.
    This allows the bot to trade bullish zones in 2023 uptrend and
    bearish zones in 2024 downtrend correctly.
    """
    candle_date = str(candle_time)[:10]

    # Find the most recent daily candle at or before candle_time
    daily_idx = None
    for i, dt in enumerate(daily_times):
        if str(dt)[:10] <= candle_date:
            daily_idx = i

    if daily_idx is None or daily_idx < 5:
        return "neutral"

    # Count bullish/bearish breaks in last 5 daily candles
    bullish_breaks = 0
    bearish_breaks = 0

    for i in range(daily_idx, max(0, daily_idx - 5), -1):
        if i >= len(daily_closes) or i - 1 < 0:
            continue
        curr_close = daily_closes[i]
        prev_high  = daily_highs[i - 1]
        prev_low   = daily_lows[i - 1]
        if curr_close > prev_high:
            bullish_breaks += 1
        elif curr_close < prev_low:
            bearish_breaks += 1

    if bullish_breaks >= 1:
        return "bullish"
    elif bearish_breaks >= 1:
        return "bearish"

    # EMA fallback on recent daily closes
    recent = daily_closes[max(0, daily_idx - 10):daily_idx + 1]
    if len(recent) >= 5:
        short_ema = sum(recent[-3:]) / 3
        long_ema  = sum(recent)      / len(recent)
        if short_ema > long_ema * 1.0002:
            return "bullish"
        elif short_ema < long_ema * 0.9998:
            return "bearish"

    return "neutral"


# ─── Liquidity Sweep Detection ────────────────────────────────────────────────

def has_liquidity_sweep(highs: list, lows: list, closes: list,
                        opens: list, i: int, zone: dict,
                        lookback: int = 5) -> bool:
    if i < lookback + 1:
        return False

    curr_high  = highs[i]
    curr_low   = lows[i]
    curr_close = closes[i]

    if zone["type"] == "demand":
        if not (curr_low < zone["bottom"] and curr_close > zone["bottom"]):
            return False
        prev_highs      = highs[max(0, i - lookback):i]
        structure_high  = max(prev_highs) if prev_highs else zone["top"]
        broke_structure = curr_close > structure_high * 0.995
        if broke_structure:
            print(f"   💧 Liquidity sweep at demand zone "
                  f"(wick: {round(curr_low,5)} < zone: {round(zone['bottom'],5)}, "
                  f"close: {round(curr_close,5)})")
            return True

    elif zone["type"] == "supply":
        if not (curr_high > zone["top"] and curr_close < zone["top"]):
            return False
        prev_lows       = lows[max(0, i - lookback):i]
        structure_low   = min(prev_lows) if prev_lows else zone["bottom"]
        broke_structure = curr_close < structure_low * 1.005
        if broke_structure:
            print(f"   💧 Liquidity sweep at supply zone "
                  f"(wick: {round(curr_high,5)} > zone: {round(zone['top'],5)}, "
                  f"close: {round(curr_close,5)})")
            return True

    return False


# ─── EMA ─────────────────────────────────────────────────────────────────────

def get_ema(closes: list, period: int) -> list:
    if len(closes) < period:
        return [None] * len(closes)
    emas = [None] * period
    ema  = sum(closes[:period]) / period
    emas.append(ema)
    k = 2 / (period + 1)
    for i in range(period + 1, len(closes)):
        ema = closes[i] * k + ema * (1 - k)
        emas.append(ema)
    return emas


# ─── HTF Bias ─────────────────────────────────────────────────────────────────

def get_htf_bias(symbol: str) -> str:
    df     = get_candles(symbol, HTF, 250)
    closes = list(df["close"])
    ema50  = get_ema(closes, 50)
    ema200 = get_ema(closes, 200)

    last50  = next((v for v in reversed(ema50)  if v is not None), None)
    last200 = next((v for v in reversed(ema200) if v is not None), None)

    if last50 is None or last200 is None:
        return "neutral"

    if last50 > last200:
        print(f"📈 H1 Bias: BULLISH (EMA50 {round(last50,5)} > EMA200 {round(last200,5)})")
        return "bullish"
    elif last50 < last200:
        print(f"📉 H1 Bias: BEARISH (EMA50 {round(last50,5)} < EMA200 {round(last200,5)})")
        return "bearish"
    return "neutral"


# ─── SL: Structural High/Low ──────────────────────────────────────────────────

def get_structure_sl(highs: list, lows: list, zone_idx: int,
                     action: str, lookback: int = 5) -> float:
    start = max(0, zone_idx - lookback)
    end   = zone_idx
    if action == "sell":
        return round(max(highs[start:end]), 5)
    else:
        return round(min(lows[start:end]), 5)


# ─── TP: Fixed RR ─────────────────────────────────────────────────────────────

def get_tp(entry: float, sl_price: float, action: str,
           rr_ratio: float = 3.0) -> tuple:
    sl_distance = abs(entry - sl_price)
    if action == "buy":
        tp1 = round(entry + sl_distance * 1.0, 5)
        tp2 = round(entry + sl_distance * rr_ratio, 5)
    else:
        tp1 = round(entry - sl_distance * 1.0, 5)
        tp2 = round(entry - sl_distance * rr_ratio, 5)
    print(f"   🎯 TP1: {tp1} | TP2: {tp2} | RR: 1:{rr_ratio}")
    return tp1, tp2, rr_ratio


# ─── Zone Quality Score ───────────────────────────────────────────────────────

def score_zone(zone: dict, trend: str) -> float:
    """Score zone based on quality and trend alignment."""
    score   = 0
    pattern = zone["pattern"]
    ztype   = zone["type"]

    # Impulse strength (max 30 points)
    score += min(zone["impulse_strength"] * 15, 30)

    # Pattern + trend alignment (max 40 points)
    if trend == "bullish":
        if ztype == "demand" and pattern == "RBR":
            score += 40   # best
        elif ztype == "demand" and pattern == "DBR":
            score += 20   # good
        else:
            score += 0    # wrong direction
    elif trend == "bearish":
        if ztype == "supply" and pattern == "DBD":
            score += 40   # best
        elif ztype == "supply" and pattern == "RBD":
            score += 30   # good
        else:
            score += 0    # wrong direction
    else:
        if pattern in ("RBR", "DBD"):
            score += 30
        elif pattern in ("DBR", "RBD"):
            score += 25
        else:
            score += 15

    # Base tightness (max 20 points)
    ratio = zone.get("base_ratio", 0.5)
    if ratio < 0.2:
        score += 20
    elif ratio < 0.3:
        score += 15
    elif ratio < 0.4:
        score += 10
    else:
        score += 5

    # Fresh zone bonus (max 10 points)
    if zone.get("fresh", True):
        score += 10

    return round(score, 1)


# ─── Zone Filter ──────────────────────────────────────────────────────────────

def zones_too_close(z1: dict, z2: dict) -> bool:
    pip     = 0.0001
    overlap = z1["bottom"] <= z2["top"] and z1["top"] >= z2["bottom"]
    if overlap:
        return True
    return abs(z1["top"] - z2["bottom"]) / pip < MIN_ZONE_PIPS


def filter_zones(zones: list, daily_trend: str,
                 min_score: float = 25.0) -> list:
    """
    Score all zones using current daily trend as reference.
    Keep ALL directions — dynamic trend filter handles direction per candle.
    """
    for z in zones:
        z["score"] = score_zone(z, daily_trend)

    # Keep all zones — direction filtered dynamically per candle
    print(f"📊 Keeping all zone directions for dynamic trend filtering")

    before = len(zones)
    zones  = [z for z in zones if z["score"] >= min_score]
    print(f"⭐ Score filter: {len(zones)} zones "
          f"(removed {before - len(zones)} below {min_score})")
    print(f"   Patterns: {set(z['pattern'] for z in zones)}")

    zones    = sorted(zones, key=lambda z: z["score"], reverse=True)
    filtered = []
    for zone in zones:
        too_close = False
        for kept in filtered:
            if kept["type"] != zone["type"]:
                continue
            if zones_too_close(zone, kept):
                too_close = True
                break
        if not too_close:
            filtered.append(zone)

    filtered.sort(key=lambda z: z["formed"])
    print(f"🔽 Final zones: {len(filtered)}\n")
    return filtered


# ─── Confirmation Candle ──────────────────────────────────────────────────────

def get_signal(opens, highs, lows, closes, i, zone_type):
    if i < 1:
        return None

    prev_o, prev_h = opens[i-1], highs[i-1]
    prev_l, prev_c = lows[i-1],  closes[i-1]
    curr_o, curr_h = opens[i],   highs[i]
    curr_l, curr_c = lows[i],    closes[i]

    prev_body = abs(prev_c - prev_o)
    curr_body = abs(curr_c - curr_o)
    curr_rng  = curr_h - curr_l

    if curr_rng == 0 or curr_body == 0:
        return None

    if zone_type == "demand":
        if (prev_c < prev_o and curr_c > curr_o and
            curr_c > prev_o and curr_o < prev_c and
            curr_body >= prev_body * 1.5):
            return "buy"
        lower = min(curr_o, curr_c) - curr_l
        if lower >= 3 * curr_body and lower > (curr_h - max(curr_o, curr_c)):
            return "buy"

    elif zone_type == "supply":
        if (prev_c > prev_o and curr_c < curr_o and
            curr_c < prev_o and curr_o > prev_c and
            curr_body >= prev_body * 1.5):
            return "sell"
        upper = curr_h - max(curr_o, curr_c)
        if upper >= 3 * curr_body and upper > (min(curr_o, curr_c) - curr_l):
            return "sell"

    return None


# ─── Momentum Filter ─────────────────────────────────────────────────────────

def is_approaching_with_contraction(opens, highs, lows, closes,
                                     i, zone, lookback=3) -> bool:
    start = max(0, i - lookback)
    if i - start < 2:
        return True

    approach_bodies = [abs(closes[j] - opens[j]) for j in range(start, i + 1)]
    approach_ranges = [highs[j] - lows[j]        for j in range(start, i + 1)]

    avg_body = sum(approach_bodies) / len(approach_bodies) if approach_bodies else 0
    if avg_body == 0:
        return True

    if approach_bodies[-1] > avg_body * 3.0:
        return False

    last_range = approach_ranges[-1]
    avg_range  = (sum(approach_ranges[:-1]) / len(approach_ranges[:-1])
                  if len(approach_ranges) > 1 else last_range)
    if last_range > avg_range * 3.0:
        return False

    if len(approach_bodies) >= 5:
        colors = ["bull" if closes[j] > opens[j] else "bear"
                  for j in range(start, i + 1)]
        if len(set(colors)) == 1:
            growing = all(approach_bodies[k] >= approach_bodies[k-1]
                          for k in range(1, len(approach_bodies)))
            if growing:
                return False
    return True


# ─── Trade Result ─────────────────────────────────────────────────────────────

class TradeResult:
    def __init__(self, action, entry, sl, tp1, tp2,
                 time, zone_score, pattern, rr_actual, session, trend):
        self.action     = action
        self.entry      = entry
        self.sl         = sl
        self.tp1        = tp1
        self.tp2        = tp2
        self.time       = time
        self.zone_score = zone_score
        self.pattern    = pattern
        self.rr_actual  = rr_actual
        self.session    = session
        self.trend      = trend
        self.status     = "open"
        self.pnl_pips   = 0.0
        self.tp1_hit    = False


# ─── Simulate Trade ───────────────────────────────────────────────────────────

def simulate_trade(trade: TradeResult, future_candles) -> TradeResult:
    pip          = 0.0001
    breakeven_sl = trade.entry
    highs        = list(future_candles["high"])
    lows         = list(future_candles["low"])

    for j in range(len(highs)):
        h = highs[j]
        l = lows[j]

        if trade.action == "buy":
            if not trade.tp1_hit:
                if l <= trade.sl:
                    trade.status   = "sl"
                    trade.pnl_pips = -abs(trade.entry - trade.sl) / pip
                    return trade
                if h >= trade.tp1:
                    trade.tp1_hit = True
                    breakeven_sl  = trade.entry
            else:
                if l <= breakeven_sl:
                    trade.status   = "breakeven"
                    trade.pnl_pips = abs(trade.tp1 - trade.entry) / pip * 0.5
                    return trade
                if h >= trade.tp2:
                    trade.status   = "tp2"
                    trade.pnl_pips = (
                        abs(trade.tp1 - trade.entry) / pip * 0.5 +
                        abs(trade.tp2 - trade.entry) / pip * 0.5
                    )
                    return trade

        elif trade.action == "sell":
            if not trade.tp1_hit:
                if h >= trade.sl:
                    trade.status   = "sl"
                    trade.pnl_pips = -abs(trade.sl - trade.entry) / pip
                    return trade
                if l <= trade.tp1:
                    trade.tp1_hit = True
                    breakeven_sl  = trade.entry
            else:
                if h >= breakeven_sl:
                    trade.status   = "breakeven"
                    trade.pnl_pips = abs(trade.entry - trade.tp1) / pip * 0.5
                    return trade
                if l <= trade.tp2:
                    trade.status   = "tp2"
                    trade.pnl_pips = (
                        abs(trade.entry - trade.tp1) / pip * 0.5 +
                        abs(trade.entry - trade.tp2) / pip * 0.5
                    )
                    return trade

    trade.status = "open"
    return trade


# ─── Save Results For MT5 ─────────────────────────────────────────────────────

def save_results_for_mt5(results: list, zones: list):
    import json, os

    trades_data = [
        {
            "time":     str(r.time),
            "action":   r.action,
            "entry":    r.entry,
            "sl":       r.sl,
            "tp1":      r.tp1,
            "tp2":      r.tp2,
            "status":   r.status,
            "pnl_pips": round(r.pnl_pips, 1),
        }
        for r in results
    ]

    zones_data = [
        {
            "type":    z["type"],
            "top":     z["top"],
            "bottom":  z["bottom"],
            "formed":  str(z["formed"]),
            "pattern": z["pattern"],
            "score":   z["score"],
        }
        for z in zones
    ]

    output = {"trades": trades_data, "zones": zones_data}

    possible_paths = [
        os.path.join(os.environ["APPDATA"],
                     "MetaQuotes", "Terminal", "Common", "Files"),
        r"C:\Users\User\AppData\Roaming\MetaQuotes\Terminal\Common\Files",
    ]

    for folder in possible_paths:
        if os.path.exists(folder):
            path = os.path.join(folder, "sd_bot_results.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2)
            print(f"💾 Results saved: {path}")
            return path

    path = os.path.join(os.getcwd(), "sd_bot_results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"⚠️  Saved locally: {path}")
    return path


# ─── Main Backtest ────────────────────────────────────────────────────────────

def run_backtest():
    print(f"\n{'='*50}")
    print(f"  🔬 BACKTEST — {SYMBOL} | {TIMEFRAME} | {CANDLES} candles")
    print(f"{'='*50}\n")

    # ── Step 1: Ranging check ──
    print("📊 Checking market structure...")
    if is_ranging(SYMBOL):
        print("⛔ Market is ranging — no trades\n")
        return []
    print()

    # ── Step 2: Fetch Daily data for dynamic trend ──
    print("📅 Fetching Daily candles for dynamic trend detection...")
    daily_df     = get_candles(SYMBOL, "D1", 500)
    daily_highs  = list(daily_df["high"])
    daily_lows   = list(daily_df["low"])
    daily_closes = list(daily_df["close"])
    daily_times  = list(daily_df.index.astype(str))
    print(f"✅ Fetched {len(daily_df)} Daily candles\n")

    # Current trend for initial zone scoring
    print("📅 Current Daily trend...")
    daily_trend = get_daily_trend(SYMBOL)
    print()

    # ── Step 3: H1 bias ──
    print("🔭 Fetching H1 bias...")
    htf_bias = get_htf_bias(SYMBOL)
    print()

    # ── Step 4: Fetch M15 data ──
    df     = get_candles(SYMBOL, TIMEFRAME, CANDLES)
    closes = list(df["close"])
    print(f"✅ Fetched {len(df)} candles ({TIMEFRAME})\n")

    diagnose_zones(df, SYMBOL)

    # ── Step 5: Indicators ──
    emas  = get_ema(closes, EMA_PERIOD)
    highs = list(df["high"])
    lows  = list(df["low"])
    opens = list(df["open"])
    times = list(df.index.astype(str))
    pip   = 0.01 if "XAU" in SYMBOL else 0.0001
    atrs  = calculate_atr(highs, lows, closes, ATR_PERIOD)

    # ── Step 6: Detect zones — keep ALL directions ──
    print("🔍 Detecting zones...")
    raw_zones = detect_zones(df, impulse_threshold=MIN_IMPULSE)
    print(f"📦 Raw zones detected: {len(raw_zones)}")
    all_zones = filter_zones(raw_zones, daily_trend, min_score=50.0)

    if not all_zones:
        print("⚠️  No zones found.")
        return []

    results      = []
    traded_zones = set()
    trend_cache  = {}  # cache trend lookups for speed

    for zone in all_zones:
        if zone["formed"] not in times:
            continue

        formed_idx = times.index(zone["formed"])
        zone_key   = (zone["formed"], zone["type"])

        if zone_key in traded_zones:
            continue

        for i in range(formed_idx + 2, len(df) - 1):
            h = highs[i]
            l = lows[i]
            c = closes[i]

            candle_in_zone = (l <= zone["top"] and h >= zone["bottom"])

            # ── Fresh zone check ──
            if zone["type"] == "demand":
                if c < zone["bottom"] * 0.999 and not candle_in_zone:
                    traded_zones.add(zone_key)
                    break
            elif zone["type"] == "supply":
                if c > zone["top"] * 1.001 and not candle_in_zone:
                    traded_zones.add(zone_key)
                    break

            if not candle_in_zone:
                continue

            # ── Session filter ──
            in_session, session_name = is_in_session(times[i])
            if not in_session:
                continue

            # ── Liquidity sweep ──
            if not has_liquidity_sweep(highs, lows, closes, opens, i, zone):
                continue

            # ── Confirmation candle ──
            signal = get_signal(opens, highs, lows, closes, i, zone["type"])
            if signal is None:
                continue

            # ── Momentum filter ──
            if not is_approaching_with_contraction(
                    opens, highs, lows, closes, i, zone):
                print(f"   ⏭ Skipped — high momentum approach")
                traded_zones.add(zone_key)
                break

            # ── Only trade bullish setups until bearish WR improves ──
            if signal == "sell":
                traded_zones.add(zone_key)
                break

            # ── Dynamic trend at time of this candle ──
            cache_key = times[i][:10]  # cache by date
            if cache_key not in trend_cache:
                trend_cache[cache_key] = get_trend_at_time(
                    daily_highs, daily_lows, daily_closes,
                    daily_times, times[i]
                )
            trend_at_time = trend_cache[cache_key]

            # Block trades against the trend at that time
            if trend_at_time == "bullish" and signal == "sell":
                traded_zones.add(zone_key)
                break
            if trend_at_time == "bearish" and signal == "buy":
                traded_zones.add(zone_key)
                break
            if trend_at_time == "neutral":
                # In neutral — use H1 bias as tiebreaker
                if htf_bias == "bullish" and signal == "sell":
                    traded_zones.add(zone_key)
                    break
                if htf_bias == "bearish" and signal == "buy":
                    traded_zones.add(zone_key)
                    break
                # If H1 also neutral — allow the trade

           
            # ── Entry at zone edge (limit order simulation) ──
            entry    = zone["top"]    if signal == "buy"  else zone["bottom"]

            # ── SL: structural high/low ──
            sl_price         = get_structure_sl(highs, lows, formed_idx, signal)
            sl_distance_pips = abs(entry - sl_price) / pip

            # ── ATR filter ──
            atr_now = atrs[i] if i < len(atrs) else None
            if atr_now is not None:
                min_sl_atr = (atr_now * ATR_MULTIPLIER) / pip
                if sl_distance_pips < min_sl_atr:
                    new_sl_dist = atr_now * ATR_MULTIPLIER
                    sl_price = (round(entry - new_sl_dist, 5)
                                if signal == "buy"
                                else round(entry + new_sl_dist, 5))
                    sl_distance_pips = abs(entry - sl_price) / pip
                    print(f"   📏 SL widened to 1.5x ATR: "
                          f"{round(sl_distance_pips,1)}p")

            if sl_distance_pips < MIN_SL_PIPS:
                print(f"   ⏭ Skipped — SL too tight ({round(sl_distance_pips,1)}p)")
                traded_zones.add(zone_key)
                break
            if sl_distance_pips > MAX_SL_PIPS:
                print(f"   ⏭ Skipped — SL too wide ({round(sl_distance_pips,1)}p)")
                traded_zones.add(zone_key)
                break

            # ── Build trade ──
            tp1, tp2, rr_actual = get_tp(entry, sl_price, signal, RR_RATIO)

            trade = TradeResult(
                action     = signal,
                entry      = entry,
                sl         = sl_price,
                tp1        = tp1,
                tp2        = tp2,
                time       = times[i],
                zone_score = zone["score"],
                pattern    = zone["pattern"],
                rr_actual  = rr_actual,
                session    = session_name,
                trend      = trend_at_time,
            )

            print(f"📊 {times[i]} [{session_name}] | {signal.upper()} | "
                  f"Trend: {trend_at_time} | Pattern: {zone['pattern']} | "
                  f"Entry: {round(entry,5)} | "
                  f"SL: {round(sl_price,5)} ({round(sl_distance_pips,1)}p) | "
                  f"TP2: {round(tp2,5)} | RR: 1:{rr_actual} | "
                  f"Score: {zone['score']}")

            future = df.iloc[i + 1:]
            trade  = simulate_trade(trade, future)
            results.append(trade)
            traded_zones.add(zone_key)

            print(f"   → {trade.status.upper()} | "
                  f"{round(trade.pnl_pips, 1)} pips\n")
            break

    return results


# ─── Report ───────────────────────────────────────────────────────────────────

def print_report(results: list):
    if not results:
        print("⚠️  No trades found.")
        return

    total       = len(results)
    wins        = [r for r in results if r.pnl_pips > 0]
    losses      = [r for r in results if r.status == "sl"]
    breakevens  = [r for r in results if r.status == "breakeven"]
    open_trades = [r for r in results if r.status == "open"]
    total_pips  = sum(r.pnl_pips for r in results)
    win_rate    = (len(wins) / total * 100) if total > 0 else 0
    avg_win     = sum(r.pnl_pips for r in wins)   / len(wins)   if wins   else 0
    avg_loss    = sum(r.pnl_pips for r in losses) / len(losses) if losses else 0
    expectancy  = total_pips / total            if total > 0 else 0
    avg_rr      = sum(r.rr_actual for r in results) / total if total > 0 else 0

    sessions = {}
    for r in results:
        s = r.session or "Unknown"
        if s not in sessions:
            sessions[s] = {"trades": 0, "pips": 0.0, "wins": 0}
        sessions[s]["trades"] += 1
        sessions[s]["pips"]   += r.pnl_pips
        if r.pnl_pips > 0:
            sessions[s]["wins"] += 1

    rbr = [r for r in results if r.pattern == "RBR"]
    dbr = [r for r in results if r.pattern == "DBR"]
    dbd = [r for r in results if r.pattern == "DBD"]
    rbd = [r for r in results if r.pattern == "RBD"]

    buys  = [r for r in results if r.action == "buy"]
    sells = [r for r in results if r.action == "sell"]

    # Trend breakdown
    bull_trades = [r for r in results if r.trend == "bullish"]
    bear_trades = [r for r in results if r.trend == "bearish"]
    bull_wins   = [r for r in bull_trades if r.pnl_pips > 0]
    bear_wins   = [r for r in bear_trades if r.pnl_pips > 0]
    bull_wr     = round(len(bull_wins) / len(bull_trades) * 100, 1) if bull_trades else 0
    bear_wr     = round(len(bear_wins) / len(bear_trades) * 100, 1) if bear_trades else 0
    bull_pips   = round(sum(r.pnl_pips for r in bull_trades), 1)
    bear_pips   = round(sum(r.pnl_pips for r in bear_trades), 1)

    if expectancy > 3:
        verdict = "✅ VIABLE — consider live testing"
    elif expectancy > 0:
        verdict = "⚠️  MARGINAL — needs more optimization"
    else:
        verdict = "❌ NOT VIABLE — needs more work"

    print(f"""
╔══════════════════════════════════════════╗
     📈 BACKTEST REPORT — {SYMBOL} {TIMEFRAME}
╠══════════════════════════════════════════╣
  Total Trades  : {total}
  Buys / Sells  : {len(buys)} / {len(sells)}
  Wins          : {len(wins)}
  Losses        : {len(losses)}
  Breakevens    : {len(breakevens)}
  Still Open    : {len(open_trades)}
  Win Rate      : {round(win_rate, 1)}%
  Total Pips    : {round(total_pips, 1)}
  Avg Win       : {round(avg_win, 1)} pips
  Avg Loss      : {round(avg_loss, 1)} pips
  Avg RR        : 1:{round(avg_rr, 2)}
  Expectancy    : {round(expectancy, 1)} pips/trade
  Verdict       : {verdict}
╠══════════════════════════════════════════╣
Pattern Breakdown:
  RBR : {len(rbr)}  DBR : {len(dbr)}
  DBD : {len(dbd)}  RBD : {len(rbd)}
╠══════════════════════════════════════════╣
  Trend Breakdown:
  Bullish trades : {len(bull_trades)} | {bull_pips} pips | {bull_wr}% WR
  Bearish trades : {len(bear_trades)} | {bear_pips} pips | {bear_wr}% WR
╠══════════════════════════════════════════╣
  Session Breakdown:""")

    for sname, sdata in sessions.items():
        wr = round(sdata["wins"] / sdata["trades"] * 100, 1) if sdata["trades"] > 0 else 0
        print(f"  {sname:<12}: {sdata['trades']} trades | "
              f"{round(sdata['pips'],1)} pips | {wr}% WR")

    print("╚══════════════════════════════════════════╝")

    print(f"\n{'#':<4} {'Time':<22} {'Sess':<10} {'Trend':<9} {'Dir':<5} "
          f"{'Pat':<5} {'Entry':<10} {'SL':<10} {'TP2':<10} "
          f"{'RR':<7} {'Score':<7} {'Result':<12} {'Pips'}")
    print("-" * 125)
    for i, r in enumerate(results, 1):
        print(f"{i:<4} {str(r.time):<22} {(r.session or 'N/A'):<10} "
              f"{(r.trend or 'N/A'):<9} "
              f"{r.action.upper():<5} {r.pattern:<5} "
              f"{round(r.entry,5):<10} {round(r.sl,5):<10} "
              f"{round(r.tp2,5):<10} 1:{r.rr_actual:<6} "
              f"{r.zone_score:<7} {r.status.upper():<12} "
              f"{round(r.pnl_pips,1)}")


# ─── Run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if connect(LOGIN, PASSWORD, SERVER):
        results = run_backtest()
        print_report(results)

        df          = get_candles(SYMBOL, TIMEFRAME, CANDLES)
        raw_zones   = detect_zones(df, impulse_threshold=MIN_IMPULSE)
        daily_trend = get_daily_trend(SYMBOL)
        zones       = filter_zones(raw_zones, daily_trend, min_score=50.0)
        save_results_for_mt5(results, zones)

        disconnect()