# telegram_bot.py
import os
import requests
import urllib3
from dotenv import load_dotenv
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import datetime

# ─── Load environment variables ───────────────────────────────────────────────

load_dotenv()

# ─── Configuration ────────────────────────────────────────────────────────────

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
BASE_URL  = "https://api.telegram.org/bot" + (BOT_TOKEN or "")

if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not found. Add it to your .env file.")
if not CHAT_ID:
    raise ValueError("TELEGRAM_CHAT_ID not found. Add it to your .env file.")


# ─── Core Send Function ───────────────────────────────────────────────────────

def send_message(text: str, parse_mode: str = "HTML") -> bool:
    """Send a message to Telegram."""
    try:
        url  = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"
        data = {
            "chat_id":    CHAT_ID,
            "text":       text,
            "parse_mode": parse_mode,
        }
        response = requests.post(url, data=data, timeout=10, verify=False)
        if response.status_code == 200:
            return True
        else:
            print(f"⚠️  Telegram error: {response.text}")
            return False
    except Exception as e:
        print(f"⚠️  Telegram send failed: {e}")
        return False


# ─── Notification Templates ───────────────────────────────────────────────────

def notify_trade_opened(trade: dict):
    """Send notification when a trade is placed."""
    action  = trade.get("action", "").upper()
    emoji   = "🟢" if action == "BUY" else "🔴"
    now     = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    msg = f"""
{emoji} <b>NEW TRADE OPENED</b>
━━━━━━━━━━━━━━━━━━━━
📌 Symbol   : <b>AUDUSD</b>
📍 Action   : <b>{action}</b>
🕐 Time     : {now}
━━━━━━━━━━━━━━━━━━━━
💰 Entry    : <b>{round(trade.get('entry', 0), 5)}</b>
🛑 SL       : <b>{round(trade.get('sl', 0), 5)}</b> ({trade.get('sl_pips', 0)}p)
🎯 TP1      : <b>{round(trade.get('tp1', 0), 5)}</b>
✅ TP2      : <b>{round(trade.get('tp2', 0), 5)}</b>
━━━━━━━━━━━━━━━━━━━━
📊 Pattern  : {trade.get('pattern', '')}
⭐ Score    : {trade.get('score', '')}
🎫 Ticket   : {trade.get('ticket', '')}
    """.strip()

    send_message(msg)


def notify_trade_closed(trade: dict, status: str, pnl_pips: float):
    """Send notification when a trade closes."""
    action = trade.get("action", "").upper()

    if status == "tp2":
        emoji  = "✅"
        result = "TP2 HIT"
    elif status == "tp1":
        emoji  = "🎯"
        result = "TP1 HIT"
    elif status == "breakeven":
        emoji  = "⚡"
        result = "BREAKEVEN"
    elif status == "sl":
        emoji  = "❌"
        result = "STOP LOSS"
    else:
        emoji  = "🔵"
        result = status.upper()

    pips_emoji = "📈" if pnl_pips > 0 else "📉" if pnl_pips < 0 else "➡️"
    now        = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    msg = f"""
{emoji} <b>TRADE CLOSED — {result}</b>
━━━━━━━━━━━━━━━━━━━━
📌 Symbol   : <b>AUDUSD</b>
📍 Action   : <b>{action}</b>
🕐 Closed   : {now}
━━━━━━━━━━━━━━━━━━━━
{pips_emoji} P&L     : <b>{'+' if pnl_pips > 0 else ''}{round(pnl_pips, 1)} pips</b>
🎫 Ticket   : {trade.get('ticket', '')}
    """.strip()

    send_message(msg)


def notify_tp1_hit(trade: dict):
    """Send notification when TP1 is hit and SL moved to breakeven."""
    msg = f"""
🎯 <b>TP1 HIT — Moving to Breakeven</b>
━━━━━━━━━━━━━━━━━━━━
📌 Symbol   : <b>AUDUSD</b>
🎫 Ticket   : {trade.get('ticket', '')}
💰 Entry    : {round(trade.get('entry', 0), 5)}
🎯 TP1      : {round(trade.get('tp1', 0), 5)} ✅
✅ TP2      : {round(trade.get('tp2', 0), 5)} 🎯 (still running)
🛡  SL moved : Breakeven ({round(trade.get('entry', 0), 5)})
    """.strip()

    send_message(msg)


def notify_signal_found(signal: dict):
    """Send notification when a signal is detected (before execution)."""
    action = signal.get("signal", "").upper()
    emoji  = "🟢" if action == "BUY" else "🔴"
    now    = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    msg = f"""
{emoji} <b>SIGNAL DETECTED</b>
━━━━━━━━━━━━━━━━━━━━
📌 Symbol   : <b>AUDUSD</b>
📍 Signal   : <b>{action}</b>
🕐 Time     : {now}
━━━━━━━━━━━━━━━━━━━━
💰 Entry    : {round(signal.get('entry', 0), 5)}
🛑 SL       : {round(signal.get('sl', 0), 5)} ({signal.get('sl_pips', 0)}p)
✅ TP2      : {round(signal.get('tp2', 0), 5)}
━━━━━━━━━━━━━━━━━━━━
📊 Pattern  : {signal.get('zone', {}).get('pattern', '')}
⭐ Score    : {signal.get('zone', {}).get('score', '')}
⏳ Placing order...
    """.strip()

    send_message(msg)


def notify_daily_summary(summary: dict):
    """Send end of day performance summary."""
    total_pips = summary.get("total_pips", 0)
    emoji      = "✅" if total_pips > 0 else "❌" if total_pips < 0 else "➡️"
    date       = datetime.datetime.now().strftime("%Y-%m-%d")

    msg = f"""
{emoji} <b>DAILY SUMMARY — {date}</b>
━━━━━━━━━━━━━━━━━━━━
📊 Trades   : {summary.get('total', 0)}
✅ Wins     : {summary.get('wins', 0)}
❌ Losses   : {summary.get('losses', 0)}
⚡ Breakevens: {summary.get('breakevens', 0)}
━━━━━━━━━━━━━━━━━━━━
📈 Total Pips: <b>{'+' if total_pips > 0 else ''}{round(total_pips, 1)}</b>
💰 Balance  : {summary.get('balance', 0)}
💵 Equity   : {summary.get('equity', 0)}
    """.strip()

    send_message(msg)


def notify_bot_started():
    """Send notification when bot starts."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = f"""
🤖 <b>SD BOT STARTED</b>
━━━━━━━━━━━━━━━━━━━━
📌 Symbol    : AUDUSD M15
🕐 Started   : {now}
📍 Strategy  : Supply & Demand
📊 Sessions  : London + New York
🎯 RR Ratio  : 1:3
✅ Bot is running and monitoring markets...
    """.strip()
    send_message(msg)


def notify_bot_stopped(reason: str = "Manual stop"):
    """Send notification when bot stops."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = f"""
🛑 <b>SD BOT STOPPED</b>
━━━━━━━━━━━━━━━━━━━━
🕐 Stopped  : {now}
📋 Reason   : {reason}
    """.strip()
    send_message(msg)


def notify_daily_loss_limit():
    """Send notification when daily loss limit is hit."""
    msg = f"""
🚨 <b>DAILY LOSS LIMIT REACHED</b>
━━━━━━━━━━━━━━━━━━━━
⛔ Trading has been paused for today.
📋 Daily max loss of 3% exceeded.
🔄 Bot will resume tomorrow.
    """.strip()
    send_message(msg)


def notify_market_ranging():
    """Send notification when market is detected as ranging."""
    msg = f"""
↔️ <b>MARKET IS RANGING</b>
━━━━━━━━━━━━━━━━━━━━
📌 Symbol : AUDUSD
⏸  No trades will be taken.
🔄 Monitoring for trend resumption...
    """.strip()
    send_message(msg)


def notify_error(error: str):
    """Send notification when bot encounters an error."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = f"""
⚠️ <b>BOT ERROR</b>
━━━━━━━━━━━━━━━━━━━━
🕐 Time   : {now}
📋 Error  : {error}
🔄 Bot will retry in 60 seconds...
    """.strip()
    send_message(msg)


# ─── Test Function ────────────────────────────────────────────────────────────

def test_connection():
    """Test that Telegram notifications are working."""
    success = send_message(
        "✅ <b>Telegram connection test successful!</b>\n"
        "Your SD Bot notifications are set up correctly. 🤖"
    )
    if success:
        print("✅ Telegram test message sent successfully!")
    else:
        print("❌ Telegram test failed — check your token and chat ID")
    return success


if __name__ == "__main__":
    test_connection()