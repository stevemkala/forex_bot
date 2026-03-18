# main.py
import time
import datetime
import MetaTrader5 as mt5
from mt5_connect import connect, disconnect
from data import get_candles, get_current_price
from strategy import detect_zones, get_daily_trend
from backtest import (
    get_ema, get_htf_bias, get_trend_at_time,
    filter_zones, get_signal, has_liquidity_sweep,
    is_approaching_with_contraction, get_tp,
    get_structure_sl, calculate_atr,
    is_ranging, score_zone,
    SYMBOL, TIMEFRAME, HTF, EMA_PERIOD,
    MIN_IMPULSE, ATR_PERIOD, ATR_MULTIPLIER,
    MIN_SL_PIPS, MAX_SL_PIPS, RR_RATIO,
    SESSIONS, LOGIN, PASSWORD, SERVER
)
from executor import (
    place_order, monitor_trades,
    close_all_positions, get_open_positions
)
from zone_manager import (
    load_zones, save_zones, update_zones,
    mark_zone_traded, get_fresh_zones_only
)
from logger import (
    log_trade, update_trade_status,
    generate_report, log_account_snapshot,
    get_daily_summary, save_report, load_logs
)
from telegram_bot import (
    notify_bot_started, notify_bot_stopped,
    notify_trade_opened, notify_trade_closed,
    notify_tp1_hit, notify_signal_found,
    notify_daily_summary, notify_daily_loss_limit,
    notify_market_ranging, notify_error
)

# ─── Configuration ────────────────────────────────────────────────────────────

CANDLES        = 500     # candles to fetch each cycle
MAX_OPEN_TRADES = 2      # max simultaneous trades
SLEEP_SECONDS  = 30      # check every 30 seconds
DAILY_MAX_LOSS = 3.0     # stop trading if daily loss > 3%

# ─── State ────────────────────────────────────────────────────────────────────

open_trades    = []      # list of active trade dicts
daily_pnl      = 0.0    # track daily P&L
last_candle    = None    # last processed candle time
zones          = []      # active zones

# ─── Helpers ──────────────────────────────────────────────────────────────────

def log(msg: str):
    """Print with timestamp."""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def is_new_candle(df) -> bool:
    """Check if a new M15 candle has closed."""
    global last_candle
    latest = str(df.index[-1])
    if latest != last_candle:
        last_candle = latest
        return True
    return False


def is_in_session() -> bool:
    """Check if current time is in a trading session."""
    now  = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    hour = now.hour
    for name, start, end in SESSIONS:
        if start <= hour < end:
            return True, name
    return False, None


def get_account_info() -> dict:
    """Get current account balance and equity."""
    info = mt5.account_info()
    if info is None:
        return {"balance": 0, "equity": 0, "profit": 0}
    return {
        "balance": info.balance,
        "equity":  info.equity,
        "profit":  info.profit,
    }


def daily_loss_exceeded() -> bool:
    """Check if daily max loss has been hit."""
    info    = get_account_info()
    balance = info["balance"]
    profit  = info["profit"]
    if balance == 0:
        return False
    loss_pct = (profit / balance) * 100
    if loss_pct <= -DAILY_MAX_LOSS:
        log(f"🛑 Daily max loss hit ({round(loss_pct,1)}%) — stopping trading")
        return True
    return False


# ─── Zone Management ──────────────────────────────────────────────────────────

def refresh_zones(df) -> list:
    """
    Detect and update zones on current data.
    Merges new zones with existing ones.
    """
    global zones

    # Get daily trend
    daily_df     = get_candles(SYMBOL, "D1", 100)
    daily_highs  = list(daily_df["high"])
    daily_lows   = list(daily_df["low"])
    daily_closes = list(daily_df["close"])
    daily_times  = list(daily_df.index.astype(str))

    current_trend = get_daily_trend(SYMBOL)

    # Detect new zones
    raw_zones = detect_zones(df, impulse_threshold=MIN_IMPULSE)
    new_zones = filter_zones(raw_zones, current_trend, min_score=50.0)

    # Update existing zones with new data
    zones = update_zones(zones, df, new_zones, save=True)
    fresh = get_fresh_zones_only(zones)

    log(f"📦 Zones: {len(fresh)} fresh | {len(zones)} total")

    # Save zones for MT5 chart drawing
    import json, os
    zones_for_chart = [
        {
            "type":    z["type"],
            "top":     z["top"],
            "bottom":  z["bottom"],
            "formed":  str(z["formed"]),
            "pattern": z["pattern"],
            "score":   z.get("score", 0),
        }
        for z in fresh
    ]

    possible_paths = [
        os.path.join(os.environ["APPDATA"],
                     "MetaQuotes", "Terminal", "Common", "Files"),
        r"C:\Users\User\AppData\Roaming\MetaQuotes\Terminal\Common\Files",
    ]
    for folder in possible_paths:
        if os.path.exists(folder):
            path = os.path.join(folder, "sd_bot_results.json")
            existing = {"trades": [], "zones": []}
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                except Exception:
                    pass
            existing["zones"] = zones_for_chart
            with open(path, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)
            break
    return fresh, current_trend, daily_highs, daily_lows, daily_closes, daily_times

    # Save live zones to MT5 chart
    import json, os
    zones_for_chart = [
        {
            "type":    z["type"],
            "top":     z["top"],
            "bottom":  z["bottom"],
            "formed":  str(z["formed"]),
            "pattern": z["pattern"],
            "score":   z.get("score", 0),
        }
        for z in fresh
    ]
    possible_paths = [
        os.path.join(os.environ["APPDATA"],
                     "MetaQuotes", "Terminal", "Common", "Files"),
        r"C:\Users\User\AppData\Roaming\MetaQuotes\Terminal\Common\Files",
    ]
    for folder in possible_paths:
        if os.path.exists(folder):
            path = os.path.join(folder, "sd_bot_results.json")
            existing = {"trades": [], "zones": []}
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                pass
            existing["zones"] = zones_for_chart
            with open(path, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)
            break


# ─── Signal Check ─────────────────────────────────────────────────────────────

def check_for_signals(df, fresh_zones, daily_highs, daily_lows,
                      daily_closes, daily_times) -> list:
    """
    Scan fresh zones for valid trade signals on latest candles.
    Returns list of trade plans ready for execution.
    """
    signals  = []
    highs    = list(df["high"])
    lows     = list(df["low"])
    opens    = list(df["open"])
    closes   = list(df["close"])
    times    = list(df.index.astype(str))
    atrs     = calculate_atr(highs, lows, closes, ATR_PERIOD)
    emas     = get_ema(closes, EMA_PERIOD)
    pip      = 0.01 if "XAU" in SYMBOL else 0.0001

    # Only check last 3 candles for fresh signals
    for i in range(max(1, len(df) - 3), len(df) - 1):
        h = highs[i]
        l = lows[i]
        c = closes[i]

        for zone in fresh_zones:
            candle_in_zone = (l <= zone["top"] and h >= zone["bottom"])
            if not candle_in_zone:
                continue

            # Liquidity sweep check
            if not has_liquidity_sweep(highs, lows, closes, opens, i, zone):
                continue

            # Confirmation candle
            signal = get_signal(opens, highs, lows, closes, i, zone["type"])
            if signal is None:
                continue

            # Only buy (bullish strategy)
            if signal == "sell":
                continue

            # Momentum filter
            if not is_approaching_with_contraction(
                    opens, highs, lows, closes, i, zone):
                continue

            # Dynamic trend at this candle
            trend_now = get_trend_at_time(
                daily_highs, daily_lows, daily_closes,
                daily_times, times[i]
            )
            if trend_now != "bullish":
                continue

            # EMA filter removed (as per optimization)

            # SL calculation
            formed_idx = times.index(zone["formed"]) if zone["formed"] in times else 0
            sl_price         = get_structure_sl(highs, lows, formed_idx, signal)
            entry            = zone["top"] if signal == "buy" else zone["bottom"]
            sl_distance_pips = abs(entry - sl_price) / pip

            # ATR filter
            atr_now = atrs[i] if i < len(atrs) else None
            if atr_now is not None:
                min_sl_atr = (atr_now * ATR_MULTIPLIER) / pip
                if sl_distance_pips < min_sl_atr:
                    new_sl_dist  = atr_now * ATR_MULTIPLIER
                    sl_price     = round(entry - new_sl_dist, 5)
                    sl_distance_pips = abs(entry - sl_price) / pip

            if sl_distance_pips < MIN_SL_PIPS or sl_distance_pips > MAX_SL_PIPS:
                continue

            # Build trade plan
            tp1, tp2, rr = get_tp(entry, sl_price, signal, RR_RATIO)

            signals.append({
                "signal":     signal,
                "entry":      entry,
                "sl":         sl_price,
                "tp1":        tp1,
                "tp2":        tp2,
                "rr":         rr,
                "zone":       zone,
                "candle_idx": i,
                "time":       times[i],
                "sl_pips":    round(sl_distance_pips, 1),
            })

            log(f"🎯 Signal: {signal.upper()} | Entry: {entry} | "
                f"SL: {sl_price} ({round(sl_distance_pips,1)}p) | "
                f"TP2: {tp2} | Zone: {zone['pattern']} Score: {zone['score']}")

    return signals


# ─── Main Loop ────────────────────────────────────────────────────────────────

def run_live():
    """
    Main live trading loop.
    Runs continuously, checking for new candles and signals.
    """
    global open_trades, zones

    log("🤖 SD Bot starting up...")
    notify_bot_started()
    log(f"   Symbol    : {SYMBOL}")
    log(f"   Timeframe : {TIMEFRAME}")
    log(f"   RR Ratio  : 1:{RR_RATIO}")
    log(f"   Max trades: {MAX_OPEN_TRADES}")
    log(f"   Sessions  : {[s[0] for s in SESSIONS]}")
    print()

    # Load saved zones from disk
    zones = load_zones()
    log(f"📂 Loaded {len(zones)} zones from disk")

    cycle = 0

    while True:
        try:
            cycle += 1

            # ── Fetch latest data ──
            df = get_candles(SYMBOL, TIMEFRAME, CANDLES)

            # ── Check for new candle ──
            if not is_new_candle(df):
                time.sleep(SLEEP_SECONDS)
                continue

            log(f"🕯  New candle — {last_candle} | Cycle #{cycle}")

            # ── Daily account snapshot at midnight ──
            now  = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            if now.hour == 0 and now.minute < 1:
                log_account_snapshot()
                info    = get_account_info()
                logs    = load_logs()
                today   = datetime.datetime.now().strftime("%Y-%m-%d")
                t_today = [t for t in logs if str(t.get("time",""))[:10] == today
                           and t.get("status") in ("tp2","tp1","sl","breakeven")]
                wins    = [t for t in t_today if t.get("pnl_pips", 0) > 0]
                losses  = [t for t in t_today if t.get("status") == "sl"]
                bes     = [t for t in t_today if t.get("status") == "breakeven"]
                total_p = sum(t.get("pnl_pips", 0) for t in t_today)

                notify_daily_summary({
                    "total":      len(t_today),
                    "wins":       len(wins),
                    "losses":     len(losses),
                    "breakevens": len(bes),
                    "total_pips": total_p,
                    "balance":    info["balance"],
                    "equity":     info["equity"],
                })
                summary = get_daily_summary()
                log(summary)
                save_report()
                log("📊 Daily report saved")

            # ── Daily loss check ──
            if daily_loss_exceeded():
                log("⛔ Trading paused — daily loss limit reached")
                notify_daily_loss_limit()
                time.sleep(300)
                continue

            # ── Session check ──
            in_session, session_name = is_in_session()
            if not in_session:
                log(f"💤 Outside trading session — waiting...")
                time.sleep(SLEEP_SECONDS)
                continue

            log(f"✅ In session: {session_name}")

            # ── Ranging market check ──
            if is_ranging(SYMBOL):
                log("↔️  Market ranging — skipping")
                time.sleep(SLEEP_SECONDS)
                continue

            # ── Monitor existing trades ──
            if open_trades:
                open_trades = monitor_trades(open_trades)
                log(f"📊 Open trades: {len(open_trades)}")

            # ── Max trades check ──
            current_open = len(get_open_positions(SYMBOL))
            if current_open >= MAX_OPEN_TRADES:
                log(f"⏸  Max trades reached ({current_open}/{MAX_OPEN_TRADES})")
                time.sleep(SLEEP_SECONDS)
                continue

            # ── Refresh zones ──
            fresh_zones, trend, d_highs, d_lows, d_closes, d_times = \
                refresh_zones(df)

            if not fresh_zones:
                log("📭 No fresh zones")
                time.sleep(SLEEP_SECONDS)
                continue

            # ── Check for signals ──
            signals = check_for_signals(
                df, fresh_zones, d_highs, d_lows, d_closes, d_times
            )

            if not signals:
                log("🔍 No signals this candle")
                time.sleep(SLEEP_SECONDS)
                continue

            # ── Execute best signal ──
            # Sort by zone score — take highest quality setup
            signals.sort(key=lambda s: s["zone"]["score"], reverse=True)
            best = signals[0]

            notify_signal_found(best)
            log(f"📤 Executing trade: {best['signal'].upper()} | "
                f"Score: {best['zone']['score']}")

            # Build trade plan for executor
            trade_plan = {
                "symbol":       SYMBOL,
                "action":       best["signal"],
                "entry":        best["entry"],
                "sl":           best["sl"],
                "tp1":          best["tp1"],
                "tp2":          best["tp2"],
                "lot_size":     0.01,   # start small — adjust later
                "sl_pips":      best["sl_pips"],
                "zone_pattern": best["zone"]["pattern"],
                "signal_type":  "live",
                "breakeven_sl": best["entry"],
                "risk_percent": 1.0,
                "risk_amount":  0,
            }

            result = place_order(trade_plan)

            if result["success"]:
                open_trades.append(result)
                zones = mark_zone_traded(zones, best["zone"])

                # ── Log the trade ──
                log_trade({
                    "ticket":   result["ticket"],
                    "time":     best["time"],
                    "symbol":   SYMBOL,
                    "action":   best["signal"],
                    "entry":    best["entry"],
                    "sl":       best["sl"],
                    "tp1":      best["tp1"],
                    "tp2":      best["tp2"],
                    "pattern":  best["zone"]["pattern"],
                    "score":    best["zone"]["score"],
                    "session":  session_name,
                    "sl_pips":  best["sl_pips"],
                    "status":   "open",
                    "pnl_pips": 0.0,
                })
                notify_trade_opened({
                    **trade_plan,
                    "ticket":   result["ticket"],
                    "sl_pips":  best["sl_pips"],
                    "pattern":  best["zone"]["pattern"],
                    "score":    best["zone"]["score"],
                })
                log(f"✅ Trade placed! Ticket: {result['ticket']}")
            else:
                log(f"❌ Trade failed: {result.get('comment', 'unknown')}")
                notify_error(f"Trade failed: {result.get('comment', 'unknown')}")

            time.sleep(SLEEP_SECONDS)

        except KeyboardInterrupt:
            log("🛑 Bot stopped by user")
            break

        except Exception as e:
            log(f"⚠️  Error: {e}")
            notify_error(str(e))
            time.sleep(60)  # wait 1 min before retry

    notify_bot_stopped()
    log("👋 Bot shutdown complete")


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if connect(LOGIN, PASSWORD, SERVER):
        try:
            run_live()
        finally:
            disconnect()