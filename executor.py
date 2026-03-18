# executor.py
import MetaTrader5 as mt5
import time

# ─── Helpers ────────────────────────────────────────────────────────────────

def get_filling_mode(symbol: str) -> int:
    """Get the correct order filling mode supported by the broker."""
    info = mt5.symbol_info(symbol)
    if info.filling_mode == 1:
        return mt5.ORDER_FILLING_RETURN
    elif info.filling_mode == 2:
        return mt5.ORDER_FILLING_IOC
    else:
        return mt5.ORDER_FILLING_FOK


def get_open_positions(symbol: str = None) -> list:
    """Return all open positions, optionally filtered by symbol."""
    positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    return list(positions) if positions else []


def get_position_by_ticket(ticket: int):
    """Fetch a single position by ticket number."""
    positions = mt5.positions_get(ticket=ticket)
    return positions[0] if positions else None


# ─── Place Order ─────────────────────────────────────────────────────────────

def place_order(trade_plan: dict) -> dict:
    """
    Place a market order with SL and TP2 as the main target.
    TP1 is managed manually (partial close).

    Returns result dict with ticket number if successful.
    """
    symbol  = trade_plan["symbol"]
    action  = trade_plan["action"]
    lot     = trade_plan["lot_size"]
    entry   = trade_plan["entry"]
    sl      = trade_plan["sl"]
    tp2     = trade_plan["tp2"]

    order_type = mt5.ORDER_TYPE_BUY if action == "buy" else mt5.ORDER_TYPE_SELL
    price      = mt5.symbol_info_tick(symbol).ask if action == "buy" else mt5.symbol_info_tick(symbol).bid

    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       symbol,
        "volume":       lot,
        "type":         order_type,
        "price":        price,
        "sl":           sl,
        "tp":           tp2,
        "deviation":    10,           # max slippage in points
        "magic":        234000,       # unique bot ID
        "comment":      f"SD_Bot | {trade_plan['zone_pattern']} | {trade_plan['signal_type']}",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": get_filling_mode(symbol),
    }

    result = mt5.order_send(request)

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"❌ Order failed — retcode: {result.retcode} | {result.comment}")
        return {"success": False, "retcode": result.retcode, "comment": result.comment}

    print(f"""
✅ Order Placed Successfully!
   Ticket  : {result.order}
   Symbol  : {symbol}
   Action  : {action.upper()}
   Lot     : {lot}
   Entry   : {result.price}
   SL      : {sl}
   TP2     : {tp2}
    """)

    return {
        "success":      True,
        "ticket":       result.order,
        "symbol":       symbol,
        "action":       action,
        "lot":          lot,
        "entry":        result.price,
        "sl":           sl,
        "tp1":          trade_plan["tp1"],
        "tp2":          tp2,
        "breakeven_sl": trade_plan["breakeven_sl"],
        "half_lot":     round(lot / 2, 2),
    }


# ─── Partial Close at TP1 ────────────────────────────────────────────────────

def partial_close(position, close_lot: float) -> bool:
    """
    Close a portion of an open position (used when TP1 is hit).
    close_lot = half the original lot size.
    """
    symbol     = position.symbol
    action     = position.type  # 0 = buy, 1 = sell
    close_type = mt5.ORDER_TYPE_SELL if action == 0 else mt5.ORDER_TYPE_BUY
    price      = mt5.symbol_info_tick(symbol).bid if action == 0 else mt5.symbol_info_tick(symbol).ask

    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       symbol,
        "volume":       close_lot,
        "type":         close_type,
        "position":     position.ticket,
        "price":        price,
        "deviation":    10,
        "magic":        234000,
        "comment":      "SD_Bot | Partial Close TP1",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": get_filling_mode(symbol),
    }

    result = mt5.order_send(request)

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"❌ Partial close failed — retcode: {result.retcode} | {result.comment}")
        return False

    print(f"✅ Partial close executed — {close_lot} lots closed at TP1")
    return True


# ─── Move SL to Breakeven ────────────────────────────────────────────────────

def move_to_breakeven(position, breakeven_sl: float) -> bool:
    """
    Modify the open position's SL to breakeven level.
    Called after TP1 partial close is successful.
    """
    request = {
        "action":   mt5.TRADE_ACTION_SLTP,
        "symbol":   position.symbol,
        "sl":       breakeven_sl,
        "tp":       position.tp,
        "position": position.ticket,
    }

    result = mt5.order_send(request)

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"❌ Breakeven move failed — retcode: {result.retcode} | {result.comment}")
        return False

    print(f"✅ SL moved to breakeven: {breakeven_sl}")
    return True


# ─── Monitor Open Trades ─────────────────────────────────────────────────────

def monitor_trades(open_trades: list[dict]) -> list[dict]:
    """
    Check each tracked trade to see if TP1 has been hit.
    If TP1 hit → partial close + move SL to breakeven.

    open_trades: list of result dicts returned by place_order()
    Returns updated list (removes fully closed trades).
    """
    still_open = []

    for trade in open_trades:
        ticket   = trade["ticket"]
        position = get_position_by_ticket(ticket)

        # Position fully closed (hit TP2 or SL)
        if position is None:
            print(f"🏁 Trade #{ticket} closed (TP2 or SL hit)")
            continue

        current_price = (
            mt5.symbol_info_tick(trade["symbol"]).bid
            if trade["action"] == "buy"
            else mt5.symbol_info_tick(trade["symbol"]).ask
        )

        tp1_hit = (
            (trade["action"] == "buy"  and current_price >= trade["tp1"]) or
            (trade["action"] == "sell" and current_price <= trade["tp1"])
        )
        already_managed = trade.get("tp1_managed", False)

        if tp1_hit and not already_managed:
                print(f"🎯 TP1 hit on trade #{ticket}...")
                closed = partial_close(position, trade["half_lot"])
                if closed:
                    move_to_breakeven(position, trade["breakeven_sl"])
                    trade["tp1_managed"] = True
                    from telegram_bot import notify_tp1_hit
                    notify_tp1_hit(trade)

        still_open.append(trade)

    return still_open


# ─── Close All Positions ─────────────────────────────────────────────────────

def close_all_positions(symbol: str = None):
    """Emergency function — close all open positions."""
    positions = get_open_positions(symbol)
    if not positions:
        print("No open positions to close.")
        return

    for pos in positions:
        close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
        price      = mt5.symbol_info_tick(pos.symbol).bid if pos.type == 0 else mt5.symbol_info_tick(pos.symbol).ask

        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       pos.symbol,
            "volume":       pos.volume,
            "type":         close_type,
            "position":     pos.ticket,
            "price":        price,
            "deviation":    10,
            "magic":        234000,
            "comment":      "SD_Bot | Emergency Close",
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": get_filling_mode(pos.symbol),
        }

        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Closed position #{pos.ticket} — {pos.symbol}")
        else:
            print(f"❌ Failed to close #{pos.ticket} — {result.comment}")
