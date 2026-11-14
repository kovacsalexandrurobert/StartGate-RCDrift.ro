"""
Board identity for Raspberry Pi Pico W and Pico 2 W.

Same application code runs on both. Flash the matching MicroPython UF2:
  - Pico W   → RPI_PICO_W
  - Pico 2 W → RPI_PICO2_W  (RP2350, preferred target)
"""


def machine_id():
    """Return os.uname().machine string, or empty on failure."""
    try:
        import os
        return os.uname().machine or ""
    except Exception:
        return ""


def is_pico2_w():
    """True when MicroPython reports a Pico 2 W / RP2350 wireless board."""
    m = machine_id().upper()
    return ("PICO 2 W" in m) or ("PICO2_W" in m) or ("RP2350" in m and "W" in m)


def is_pico_w():
    """True for original Pico W (RP2040 + CYW43)."""
    m = machine_id().upper()
    if is_pico2_w():
        return False
    return ("PICO W" in m) or ("PICO_W" in m)


def short_name():
    """Human label for logs / OLED-friendly status."""
    if is_pico2_w():
        return "Pico 2 W"
    if is_pico_w():
        return "Pico W"
    m = machine_id()
    return m[:20] if m else "unknown"


def log_boot():
    """Print board line once at boot. Safe if uname is missing."""
    name = short_name()
    mid = machine_id()
    print("[Board] %s" % name)
    if mid:
        print("[Board] machine=%s" % mid)
    return name
