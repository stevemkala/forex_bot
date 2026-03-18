# risk.py
import MetaTrader5 as mt5

def get_account_balance() -> float:
    """Get current account balance."""
    info = mt5.account_info()
    if info is None:
        raise RuntimeError("Cannot retrieve account info")
    return info.balance


def get_pip_value(symbol: str, lot_size: float) -> float:
    """
    Calculate pip value in account currency for a given lot size.
    For most forex pairs, 1 pip = 0.0001 (except JPY pairs = 0.01)
    """
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        raise RuntimeError(f"Cannot get symbol info for {symbol}")

    pip        = 0.01 if "JPY" in symbol else 0.0001
    point      = symbol_info.point
    pip_points = pip / point  # how many points = 1 pip

    # Pip value = (pip / price) * lot * contract_size  [approximation for non-USD base]
    tick_value = symbol_info.trade_tick_value
    tick_size  = symbol_info.trade_tick_size
    pip_value  = (pip / tick_size) * tick_value * lot_size
    return round(pip_value, 4)


def calculate_lot_size(
    symbol: str,
    sl_pips: float,
    risk_percent: float = 1.0,
) -> float:
    """
    Calculate lot size based on:
    - Account balance
    - Risk % per trade (default 1%)
    - Stop loss distance in pips

    Formula: Lot = (Balance * Risk%) / (SL in pips * Pip Value per lot)
    """
    balance      = get_account_balance()
    risk_amount  = balance * (risk_percent / 100)

    # Pip value for 1 standard lot
    pip_value_per_lot = get_pip_value(symbol, lot_size=1.0)

    if pip_value_per_lot == 0 or sl_pips == 0:
        raise ValueError("SL pips or pip value cannot be zero")

    raw_lot = risk_amount / (sl_pips * pip_value_per_lot)

    # Snap to broker's allowed lot step (e.g. 0.01)
    symbol_info  = mt5.symbol_info(symbol)
    lot_step     = symbol_info.volume_step
    min_lot      = symbol_info.volume_min
    max_lot      = symbol_info.volume_max

    lot = round(raw_lot / lot_step) * lot_step
    lot = max(min_lot, min(max_lot, lot))  # clamp within broker limits

    return round(lot, 2)


def calculate_levels(
    action: str,
    entry: float,
    sl_price: float,
    symbol: str,
    rr_ratio: float = 2.0,
) -> dict:
    """
    Calculate:
    - SL price (already provided from zone)
    - TP1 at 1:1 Risk:Reward  (partial close here, trail to BE)
    - TP2 at 1:2 Risk:Reward  (final target)
    - SL distance in pips
    """
    pip = 0.01 if "JPY" in symbol else 0.0001

    sl_distance       = abs(entry - sl_price)
    sl_pips           = round(sl_distance / pip, 1)
    tp1_distance      = sl_distance * 1.0   # 1:1
    tp2_distance      = sl_distance * rr_ratio  # 1:2 default

    if action == "buy":
        tp1 = round(entry + tp1_distance, 5)
        tp2 = round(entry + tp2_distance, 5)
    else:  # sell
        tp1 = round(entry - tp1_distance, 5)
        tp2 = round(entry - tp2_distance, 5)

    return {
        "entry":      entry,
        "sl":         round(sl_price, 5),
        "tp1":        tp1,
        "tp2":        tp2,
        "sl_pips":    sl_pips,
        "rr_ratio":   rr_ratio,
    }


def calculate_breakeven(action: str, entry: float, symbol: str, buffer_pips: float = 1.0) -> float:
    """
    Calculate breakeven SL level with a small buffer above/below entry.
    Called after TP1 is hit to move SL to entry + buffer.
    """
    pip    = 0.01 if "JPY" in symbol else 0.0001
    buffer = buffer_pips * pip

    if action == "buy":
        return round(entry + buffer, 5)
    else:
        return round(entry - buffer, 5)


def build_trade_plan(
    signal: dict,
    symbol: str,
    risk_percent: float = 1.0,
    rr_ratio: float = 2.0,
) -> dict:
    """
    Master function — takes a raw signal and returns a complete trade plan.

    Input signal (from entry.py):
        action, entry_price, sl_price, zone, signal_type

    Output trade plan:
        action, entry, sl, tp1, tp2, sl_pips, lot_size, breakeven_sl, risk_amount
    """
    levels   = calculate_levels(
        action    = signal["action"],
        entry     = signal["entry_price"],
        sl_price  = signal["sl_price"],
        symbol    = symbol,
        rr_ratio  = rr_ratio,
    )

    lot_size = calculate_lot_size(
        symbol       = symbol,
        sl_pips      = levels["sl_pips"],
        risk_percent = risk_percent,
    )

    balance      = get_account_balance()
    risk_amount  = round(balance * (risk_percent / 100), 2)
    be_sl        = calculate_breakeven(signal["action"], levels["entry"], symbol)

    trade_plan = {
        "action":        signal["action"],
        "symbol":        symbol,
        "signal_type":   signal["signal_type"],
        "zone_type":     signal["zone"]["type"],
        "zone_pattern":  signal["zone"]["pattern"],
        "entry":         levels["entry"],
        "sl":            levels["sl"],
        "tp1":           levels["tp1"],
        "tp2":           levels["tp2"],
        "sl_pips":       levels["sl_pips"],
        "rr_ratio":      rr_ratio,
        "lot_size":      lot_size,
        "breakeven_sl":  be_sl,
        "risk_percent":  risk_percent,
        "risk_amount":   risk_amount,
    }

    # ── Pretty print the plan ──
    print(f"""
╔══════════════════════════════════════╗
         📋 TRADE PLAN — {symbol}
╠══════════════════════════════════════╣
  Action      : {trade_plan['action'].upper()}
  Signal      : {trade_plan['signal_type']} at {trade_plan['zone_type']} zone ({trade_plan['zone_pattern']})
  Entry       : {trade_plan['entry']}
  Stop Loss   : {trade_plan['sl']}  ({trade_plan['sl_pips']} pips)
  TP1 (1:1)   : {trade_plan['tp1']}
  TP2 (1:{rr_ratio}) : {trade_plan['tp2']}
  Breakeven   : {trade_plan['breakeven_sl']} (after TP1 hit)
  Lot Size    : {trade_plan['lot_size']}
  Risk        : {trade_plan['risk_percent']}% = ${trade_plan['risk_amount']}
╚══════════════════════════════════════╝
    """)

    return trade_plan