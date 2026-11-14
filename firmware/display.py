"""
Status display for Start Light - SSD1306 128x64 I2C OLED.
Shows: BLE steps, WiFi status, IP address.
Optional - no-op if display not connected or disabled.

Uses SoftI2C (not hardware I2C): RP2 hard I2C commonly raises
ETIMEDOUT/EIO with SSD1306 modules; SoftI2C on GP6/GP7 is reliable.
"""

import time

_oled = None
_enabled = True
_init_failed_logged = False


def reset_oled_cache():
    """Clear cached OLED instance (e.g. after WiFi/BLE radio changes)."""
    global _oled
    _oled = None


def _pins():
    try:
        from config import DISPLAY_SDA, DISPLAY_SCL, DISPLAY_ENABLED
        if not DISPLAY_ENABLED:
            return None
        return DISPLAY_SDA, DISPLAY_SCL
    except Exception:
        return 6, 7  # GP6, GP7 default


def _pick_addr(i2c):
    """Prefer 0x3C; accept 0x3D (common alternate)."""
    try:
        found = i2c.scan()
    except Exception:
        found = []
    if 0x3C in found:
        return 0x3C
    if 0x3D in found:
        return 0x3D
    # Scan empty (noisy bus / mid-init): still try default
    return 0x3C


def _make_i2c(sda, scl, freq):
    import machine
    # SoftI2C: hardware I2C on RP2 often ETIMEDOUT/EIO with SSD1306
    sda_pin = machine.Pin(sda)
    scl_pin = machine.Pin(scl)
    try:
        return machine.SoftI2C(sda=sda_pin, scl=scl_pin, freq=freq, timeout=50000)
    except TypeError:
        return machine.SoftI2C(sda=sda_pin, scl=scl_pin, freq=freq)


def _try_open(sda, scl, freq):
    from ssd1306 import SSD1306_I2C
    i2c = _make_i2c(sda, scl, freq)
    time.sleep_ms(20)
    addr = _pick_addr(i2c)
    return SSD1306_I2C(128, 64, i2c, addr=addr)


def _init():
    global _oled, _init_failed_logged
    if _oled is not None:
        return _oled
    if not _enabled:
        return None
    pins = _pins()
    if pins is None:
        return None
    sda, scl = pins

    last_err = None
    for freq in (100000, 400000):
        for attempt in range(2):
            try:
                _oled = _try_open(sda, scl, freq)
                print("[Display] OLED OK SoftI2C GP%d/GP%d @ %d Hz addr=0x%02X" % (
                    sda, scl, freq, _oled.addr))
                _init_failed_logged = False
                return _oled
            except Exception as e:
                last_err = e
                _oled = None
                time.sleep_ms(50)

    if not _init_failed_logged:
        print("[Display] Not available:", last_err)
        _init_failed_logged = True
    return None


def show_lines(*lines):
    """Show up to 4 lines of text (8px font). Truncates long lines."""
    oled = _init()
    if not oled:
        return
    try:
        oled.fill(0)
        for i, line in enumerate(lines[:4]):
            s = str(line)[:21]  # ~21 chars fit at 8px
            oled.text(s, 0, i * 10)
        oled.show()
    except Exception as e:
        # Bus glitch after WiFi/BLE — drop cache and retry once
        print("[Display] Write failed, retry:", e)
        reset_oled_cache()
        oled = _init()
        if not oled:
            return
        try:
            oled.fill(0)
            for i, line in enumerate(lines[:4]):
                s = str(line)[:21]
                oled.text(s, 0, i * 10)
            oled.show()
        except Exception as e2:
            print("[Display] Retry failed:", e2)
            reset_oled_cache()


def show(msg):
    """Show single message (wraps into 2 lines if needed)."""
    msg = str(msg)
    if len(msg) <= 21:
        show_lines(msg)
    else:
        parts = []
        while msg:
            parts.append(msg[:21])
            msg = msg[21:]
        show_lines(*parts[:4])


def show_boot():
    """Boot/self-test phase."""
    show_lines("Start Light", "Self-test...", "", "")


def show_wifi_connecting(ssid=""):
    """WiFi connecting phase."""
    show_lines("WiFi", "Connecting...", ssid[:21] if ssid else "", "")


def show_wifi_connected(ssid=""):
    """WiFi connected."""
    show_lines("WiFi OK", ssid[:21] if ssid else "", "", "")


def show_wifi_failed():
    """WiFi failed."""
    show_lines("WiFi failed", "Retrying...", "", "")


def show_ble_waiting():
    """BLE mode - waiting for credentials or BLE START."""
    show_lines("BLE mode", "WiFi or START", "SSID,pass,RO", "nRF Connect")


def show_ble_pin(pin):
    """BLE mode - show 6-digit PIN for connection confirmation."""
    if pin is None:
        pin_str = "------"
    else:
        try:
            n = int(pin) % 1000000
        except (ValueError, TypeError):
            n = 0
        pin_str = "%06d" % n  # MicroPython str has no zfill on some builds
    show_lines("BLE PIN", pin_str, "Enter to connect", "")


def show_ble_received():
    """BLE - credentials received."""
    show_lines("BLE OK", "Saved!", "Rebooting...", "")


def show_ip(ip):
    """Show assigned IP address. URL is split across lines (full http:// + IP is >21 chars)."""
    ip = str(ip).strip()
    if len(ip) <= 21:
        show_lines("Ready!", "http://", ip, "")
    else:
        # Long IPv6 etc.: continue IP on line 4
        show_lines("Ready!", "http://", ip[:21], ip[21:42])


def clear():
    """Clear display."""
    oled = _init()
    if oled:
        try:
            oled.fill(0)
            oled.show()
        except Exception:
            reset_oled_cache()


def off():
    """Turn display off (power save)."""
    oled = _init()
    if oled:
        try:
            oled.poweroff()
        except Exception:
            reset_oled_cache()
