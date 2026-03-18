# test_connection.py
import time
from mt5_connect import connect, disconnect

LOGIN    = 335705          # ← your account number
PASSWORD = "Av3ng3r$"    # ← your password
SERVER   = "EGMSecurities-Demo"  # ← your server name

if connect(LOGIN, PASSWORD, SERVER):
    print("🎉 Connection successful!")
    time.sleep(2)   # ← give MT5 a moment before disconnecting
    disconnect()
