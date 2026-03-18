# mt5_connect.py
import MetaTrader5 as mt5
import time

def connect(login: int, password: str, server: str) -> bool:
    """Initialize and log in to MetaTrader 5 with retry logic."""

    # Step 1: Initialize MT5
    if not mt5.initialize():
        print(f"❌ MT5 initialize() failed — error: {mt5.last_error()}")
        return False

    # Step 2: Wait for terminal to stabilize
    print("⏳ Waiting for MT5 terminal to stabilize...")
    time.sleep(3)

    # Step 3: Try login up to 3 times
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        print(f"🔄 Login attempt {attempt}/{max_retries}...")

        authorized = mt5.login(
            login    = login,
            password = password,
            server   = server
        )

        if authorized:
            break

        error = mt5.last_error()
        print(f"⚠️  Attempt {attempt} failed — error: {error}")
        time.sleep(3)  # wait before retrying

    if not authorized:
        print("❌ All login attempts failed. Check credentials and server name.")
        mt5.shutdown()
        return False

    # Step 4: Wait for account to fully connect
    print("⏳ Waiting for account to connect...")
    for _ in range(10):
        info = mt5.account_info()
        if info is not None:
            break
        time.sleep(1)
    else:
        print("❌ Account info unavailable after login. MT5 may still be connecting.")
        mt5.shutdown()
        return False

    print(f"✅ Connected to {info.server} | Account: {info.login} | Balance: {info.balance} {info.currency}")
    return True


def disconnect():
    """Cleanly shut down the MT5 connection."""
    mt5.shutdown()
    print("🔌 Disconnected from MT5")