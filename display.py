"""
Status display for Start Light - SSD1306 128x64 I2C OLED.
Shows: BLE steps, WiFi status, IP address.
Optional - no-op if display not connected or disabled.
"""

_oled = None
_enabled = True


def reset_oled_cache():
    """Clear cached OLED instance (e.g. after WiFi off, before BLE + I2C redraw)."""
    global _oled
    _oled = None


def _init():
    global _oled
    if _oled is not None:
        return _oled
    if not _enabled:
        return None
    try:
        from config import DISPLAY_SDA, DISPLAY_SCL, DISPLAY_ENABLED
        if not DISPLAY_ENABLED:
            return None
        sda, scl = DISPLAY_SDA, DISPLAY_SCL
    except Exception:
        sda, scl = 6, 7  # GP6, GP7 default
    try:
        import machine
        from ssd1306 import SSD1306_I2C
        i2c = machine.I2C(1, sda=machine.Pin(sda), scl=machine.Pin(scl), freq=400000)
        _oled = SSD1306_I2C(128, 64, i2c, addr=0x3C)
        return _oled
    except Exception as e:
        print("[Display] Not available:", e)
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
    except Exception:
        pass


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
            pass


def off():
    """Turn display off (power save)."""
    oled = _init()
    if oled:
        try:
            oled.poweroff()
        except Exception:
            pass
