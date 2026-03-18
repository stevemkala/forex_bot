# logger.py
import os
import json
import datetime
import MetaTrader5 as mt5


# ─── Configuration ────────────────────────────────────────────────────────────

LOG_FILE    = "trade_log.json"
REPORT_FILE = "performance_report.txt"


# ─── Trade Logger ─────────────────────────────────────────────────────────────

def log_trade(trade: dict):
    """
    Save a completed trade to the trade log JSON file.
    Called when a trade is opened, closed, or updated.
    """
    logs = load_logs()
    
    # Add timestamp
    trade["logged_at"] = str(datetime.datetime.now())
    logs.append(trade)
    
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2)


def load_logs() -> list:
    """Load all trade logs from disk."""
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def update_trade_status(ticket: int, status: str, pnl_pips: float):
    """Update an existing trade's status when it closes."""
    logs = load_logs()
    for trade in logs:
        if trade.get("ticket") == ticket:
            trade["status"]   = status
            trade["pnl_pips"] = round(pnl_pips, 1)
            trade["closed_at"] = str(datetime.datetime.now())
            break
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2)


# ─── Performance Report ───────────────────────────────────────────────────────

def generate_report() -> str:
    """
    Generate a full performance report from trade logs.
    Returns formatted string report.
    """
    logs = load_logs()
    
    if not logs:
        return "⚠️  No trades logged yet."

    # Filter closed trades only
    closed = [t for t in logs if t.get("status") in
              ("tp2", "tp1", "sl", "breakeven")]

    if not closed:
        return "⚠️  No closed trades yet."

    total      = len(closed)
    wins       = [t for t in closed if t.get("pnl_pips", 0) > 0]
    losses     = [t for t in closed if t.get("status") == "sl"]
    breakevens = [t for t in closed if t.get("status") == "breakeven"]
    total_pips = sum(t.get("pnl_pips", 0) for t in closed)
    win_rate   = (len(wins) / total * 100) if total > 0 else 0
    avg_win    = sum(t.get("pnl_pips", 0) for t in wins) / len(wins) if wins else 0
    avg_loss   = sum(t.get("pnl_pips", 0) for t in losses) / len(losses) if losses else 0
    expectancy = total_pips / total if total > 0 else 0

    # Session breakdown
    sessions = {}
    for t in closed:
        s = t.get("session", "Unknown")
        if s not in sessions:
            sessions[s] = {"trades": 0, "pips": 0.0, "wins": 0}
        sessions[s]["trades"] += 1
        sessions[s]["pips"]   += t.get("pnl_pips", 0)
        if t.get("pnl_pips", 0) > 0:
            sessions[s]["wins"] += 1

    # Pattern breakdown
    patterns = {}
    for t in closed:
        p = t.get("pattern", "Unknown")
        if p not in patterns:
            patterns[p] = {"trades": 0, "pips": 0.0, "wins": 0}
        patterns[p]["trades"] += 1
        patterns[p]["pips"]   += t.get("pnl_pips", 0)
        if t.get("pnl_pips", 0) > 0:
            patterns[p]["wins"] += 1

    # Weekly breakdown
    weekly = {}
    for t in closed:
        try:
            date = t.get("time", "")[:10]
            dt   = datetime.datetime.strptime(date, "%Y-%m-%d")
            week = f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"
        except Exception:
            week = "Unknown"
        if week not in weekly:
            weekly[week] = {"trades": 0, "pips": 0.0, "wins": 0}
        weekly[week]["trades"] += 1
        weekly[week]["pips"]   += t.get("pnl_pips", 0)
        if t.get("pnl_pips", 0) > 0:
            weekly[week]["wins"] += 1

    if expectancy > 3:
        verdict = "✅ PERFORMING WELL"
    elif expectancy > 0:
        verdict = "⚠️  MARGINAL"
    else:
        verdict = "❌ REVIEW STRATEGY"

    # Build report string
    now    = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report = f"""
╔══════════════════════════════════════════╗
     📈 LIVE PERFORMANCE REPORT
     Generated: {now}
╠══════════════════════════════════════════╣
  Symbol        : AUDUSD M15
  Total Trades  : {total}
  Wins          : {len(wins)}
  Losses        : {len(losses)}
  Breakevens    : {len(breakevens)}
  Win Rate      : {round(win_rate, 1)}%
  Total Pips    : {round(total_pips, 1)}
  Avg Win       : {round(avg_win, 1)} pips
  Avg Loss      : {round(avg_loss, 1)} pips
  Expectancy    : {round(expectancy, 1)} pips/trade
  Verdict       : {verdict}
╠══════════════════════════════════════════╣
  Pattern Breakdown:"""

    for pat, data in sorted(patterns.items()):
        wr = round(data["wins"] / data["trades"] * 100, 1) if data["trades"] > 0 else 0
        report += f"\n  {pat:<6}: {data['trades']} trades | {round(data['pips'],1)} pips | {wr}% WR"

    report += "\n╠══════════════════════════════════════════╣"
    report += "\n  Session Breakdown:"
    for sess, data in sorted(sessions.items()):
        wr = round(data["wins"] / data["trades"] * 100, 1) if data["trades"] > 0 else 0
        report += f"\n  {sess:<12}: {data['trades']} trades | {round(data['pips'],1)} pips | {wr}% WR"

    report += "\n╠══════════════════════════════════════════╣"
    report += "\n  Weekly Breakdown:"
    for week, data in sorted(weekly.items()):
        wr = round(data["wins"] / data["trades"] * 100, 1) if data["trades"] > 0 else 0
        report += f"\n  {week}: {data['trades']} trades | {round(data['pips'],1)} pips | {wr}% WR"

    report += "\n╠══════════════════════════════════════════╣"
    report += "\n  Trade History:"
    report += f"\n  {'#':<4} {'Time':<22} {'Dir':<5} {'Pat':<5} {'Entry':<10} {'SL':<10} {'TP2':<10} {'Status':<12} {'Pips'}"
    report += "\n  " + "-" * 85

    for i, t in enumerate(closed, 1):
        report += (
            f"\n  {i:<4} {str(t.get('time',''))[:19]:<22} "
            f"{t.get('action','').upper():<5} "
            f"{t.get('pattern',''):<5} "
            f"{round(t.get('entry',0),5):<10} "
            f"{round(t.get('sl',0),5):<10} "
            f"{round(t.get('tp2',0),5):<10} "
            f"{t.get('status','').upper():<12} "
            f"{round(t.get('pnl_pips',0),1)}"
        )

    report += "\n╚══════════════════════════════════════════╝"
    return report


# ─── Account Snapshot ─────────────────────────────────────────────────────────

def log_account_snapshot():
    """Log daily account balance snapshot."""
    info = mt5.account_info()
    if info is None:
        return

    snapshot_file = "account_snapshots.json"
    snapshots     = []

    if os.path.exists(snapshot_file):
        with open(snapshot_file, "r", encoding="utf-8") as f:
            snapshots = json.load(f)

    snapshots.append({
        "time":    str(datetime.datetime.now()),
        "balance": info.balance,
        "equity":  info.equity,
        "profit":  info.profit,
        "margin":  info.margin,
    })

    with open(snapshot_file, "w", encoding="utf-8") as f:
        json.dump(snapshots, f, indent=2)


# ─── Daily Summary ────────────────────────────────────────────────────────────

def get_daily_summary() -> str:
    """Get summary of today's trades only."""
    logs  = load_logs()
    today = datetime.datetime.now().strftime("%Y-%m-%d")

    today_trades = [
        t for t in logs
        if str(t.get("time", ""))[:10] == today
        and t.get("status") in ("tp2", "tp1", "sl", "breakeven")
    ]

    if not today_trades:
        return f"📅 No trades today ({today})"

    total_pips = sum(t.get("pnl_pips", 0) for t in today_trades)
    wins       = [t for t in today_trades if t.get("pnl_pips", 0) > 0]
    losses     = [t for t in today_trades if t.get("status") == "sl"]

    emoji = "✅" if total_pips > 0 else "❌"

    summary = f"""
{emoji} Daily Summary — {today}
Trades : {len(today_trades)}
Wins   : {len(wins)} | Losses: {len(losses)}
Pips   : {round(total_pips, 1)}
    """
    return summary.strip()


# ─── Save Report To File ──────────────────────────────────────────────────────

def save_report():
    """Save full performance report to text file."""
    report = generate_report()
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"💾 Report saved to {REPORT_FILE}")
    return report