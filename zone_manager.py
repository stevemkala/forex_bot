# zone_manager.py
import json
import os
import numpy as np
import pandas as pd
from datetime import datetime

ZONES_FILE = "zones_state.json"


# ─── Save / Load Zones ───────────────────────────────────────────────────────

def save_zones(zones: list[dict]):
    """Save current zone state to disk so it persists across restarts."""
    serializable = []
    for z in zones:
        zc = z.copy()
        zc["formed"] = str(zc["formed"])
        serializable.append(zc)

    with open(ZONES_FILE, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2)
    print(f"💾 Zones saved ({len(zones)} total)")


def load_zones() -> list[dict]:
    """Load zones from disk if they exist."""
    if not os.path.exists(ZONES_FILE):
        return []
    try:
        with open(ZONES_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return []
            zones = json.loads(content)
        print(f"📂 Loaded {len(zones)} zones from disk")
        return zones
    except Exception as e:
        print(f"⚠️  Could not load zones: {e} — starting fresh")
        return []


# ─── Zone Touch Detection ─────────────────────────────────────────────────────

def price_inside_zone(price: float, zone: dict, buffer_pips: float = 2.0) -> bool:
    """Check if a price level is inside or within buffer of a zone."""
    pip    = 0.01 if "JPY" in zone.get("symbol", "") else 0.0001
    buffer = buffer_pips * pip
    return (zone["bottom"] - buffer) <= price <= (zone["top"] + buffer)


def has_candle_touched_zone(high: float, low: float, zone: dict) -> bool:
    """Check if a candle's high/low has touched or entered the zone."""
    return low <= zone["top"] and high >= zone["bottom"]


# ─── Invalidation Logic ───────────────────────────────────────────────────────

def invalidate_touched_zones(zones: list[dict], df: pd.DataFrame) -> list[dict]:
    if not zones or len(df) == 0:
        return zones

    highs = list(df["high"])
    lows  = list(df["low"])
    times = list(df.index.astype(str))

    for zone in zones:
        if not zone["fresh"]:
            continue
        formed = str(zone["formed"])
        for j in range(len(times)):
            if times[j] <= formed:
                continue
            if lows[j] <= zone["top"] and highs[j] >= zone["bottom"]:
                zone["fresh"]       = False
                zone["invalidated"] = times[j]
                zone["reason"]      = "price_touched"
                break

    return zones


def invalidate_broken_zones(zones: list[dict], df: pd.DataFrame) -> list[dict]:
    if not zones or len(df) == 0:
        return zones

    closes = list(df["close"])
    times  = list(df.index.astype(str))

    for zone in zones:
        if not zone["fresh"]:
            continue
        formed = str(zone["formed"])
        for j in range(len(times)):
            if times[j] <= formed:
                continue
            if zone["type"] == "demand" and closes[j] < zone["bottom"]:
                zone["fresh"]       = False
                zone["invalidated"] = times[j]
                zone["reason"]      = "structure_broken"
                break
            if zone["type"] == "supply" and closes[j] > zone["top"]:
                zone["fresh"]       = False
                zone["invalidated"] = times[j]
                zone["reason"]      = "structure_broken"
                break

    return zones


# ─── Mark Zone As Traded ─────────────────────────────────────────────────────

def mark_zone_traded(zones: list[dict], zone_to_mark: dict) -> list[dict]:
    """After a trade is placed, permanently mark zone as used."""
    for zone in zones:
        if (
            str(zone["formed"]) == str(zone_to_mark["formed"]) and
            zone["type"]        == zone_to_mark["type"]
        ):
            zone["fresh"]     = False
            zone["reason"]    = "traded"
            zone["traded_at"] = str(datetime.now())
            print(f"🔒 Zone marked as traded: {zone['type']} | {zone['pattern']} | formed {zone['formed']}")
            break

    return zones


# ─── Master Update Function ───────────────────────────────────────────────────

def update_zones(zones: list[dict], df, new_zones: list[dict] = None, save: bool = True) -> list[dict]:
    """
    Full zone update pipeline called on every candle:
    1. Merge any newly detected zones
    2. Invalidate touched zones
    3. Invalidate structurally broken zones
    4. Optionally save to disk (disable during backtesting)
    5. Return all zones
    """
    # 1. Merge new zones
    if new_zones:
        existing_keys = {(str(z["formed"]), z["type"]) for z in zones}
        for z in new_zones:
            key = (str(z["formed"]), z["type"])
            if key not in existing_keys:
                zones.append(z)
                print(f"➕ New zone added: {z['type']} | {z['pattern']} | formed {z['formed']}")

    # 2. Invalidate touched
    zones = invalidate_touched_zones(zones, df)

    # 3. Invalidate broken
    zones = invalidate_broken_zones(zones, df)

    # 4. Save only during live trading
    if save:
        save_zones(zones)

    # 5. Summary
    fresh = [z for z in zones if z["fresh"]]
    stale = [z for z in zones if not z["fresh"]]
    print(f"🗂  Zones — Fresh: {len(fresh)} | Invalidated: {len(stale)}")

    return zones


def get_fresh_zones_only(zones: list[dict]) -> list[dict]:
    """Return only zones that are still fresh and tradeable."""
    return [z for z in zones if z["fresh"]]