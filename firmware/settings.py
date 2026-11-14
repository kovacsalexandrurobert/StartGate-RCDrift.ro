"""
Light settings storage - persisted to startlight_config.json on device.
Editable via web settings page.
"""

import json
import os
from config import (
    CONFIG_FILE,
    RED_DURATION, RANDOM_WAIT_MIN, RANDOM_WAIT_MAX,
    YELLOW_INTERVAL, GREEN_OFF_DELAY,
    START_DELAY_MODE, START_DELAY_FIXED,
    START_DELAY_RANDOM_MIN, START_DELAY_RANDOM_MAX,
)


DEFAULTS = {
    "red_duration": RED_DURATION,
    "random_wait_min": RANDOM_WAIT_MIN,
    "random_wait_max": RANDOM_WAIT_MAX,
    "yellow_interval": YELLOW_INTERVAL,
    "green_off_delay": GREEN_OFF_DELAY,
    "start_delay_mode": START_DELAY_MODE,  # 0=random, 1=fixed
    "start_delay_fixed": START_DELAY_FIXED,
    "start_delay_random_min": START_DELAY_RANDOM_MIN,
    "start_delay_random_max": START_DELAY_RANDOM_MAX,
}


def load():
    """Load settings from file"""
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            result = DEFAULTS.copy()
            result.update(data)
            print("[Settings] Loaded from %s" % CONFIG_FILE)
            return result
    except (OSError, ValueError):
        print("[Settings] Using defaults (no file or invalid)")
        return DEFAULTS.copy()


def save(settings):
    """Save settings to file"""
    with open(CONFIG_FILE, "w") as f:
        json.dump(settings, f)
    print("[Settings] Saved to %s" % CONFIG_FILE)


def get_start_delay(settings):
    """Get start delay in seconds based on settings"""
    if settings["start_delay_mode"] == 1:
        return float(settings["start_delay_fixed"])
    import random
    return random.uniform(
        settings["start_delay_random_min"],
        settings["start_delay_random_max"]
    )
