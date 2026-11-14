"""
Onboard LED for wireless connection debug status.

Pico W and Pico 2 W: Pin("LED") drives the LED through the CYW43.
"""

import machine
import time

try:
    _led = machine.Pin("LED", machine.Pin.OUT)
except Exception:
    _led = None  # Missing on non-wireless Pico boards


def _safe(value):
    """Set LED state if available"""
    if _led is not None:
        _led.value(value)


def off():
    _safe(0)


def on():
    _safe(1)


def blink(count, on_ms=200, off_ms=200):
    """Blink LED count times"""
    if _led is None:
        return
    for _ in range(count):
        _led.on()
        time.sleep_ms(on_ms)
        _led.off()
        time.sleep_ms(off_ms)


def status_not_connected():
    """Not connected: blink 3 times, wait 3 sec"""
    blink(3, 200, 200)
    time.sleep(3)


def status_connecting_tick(elapsed_ms):
    """Connecting: blink every second (flash 200ms on, 800ms off per second)."""
    if _led is None:
        return
    pos_in_sec = elapsed_ms % 1000
    _led.value(1 if pos_in_sec < 200 else 0)


def status_ble_tick(elapsed_ms):
    """BLE awaiting: ON 2 sec, OFF 1 sec. Call from BLE wait loop each 100ms."""
    if _led is None:
        return
    cycle_ms = 3000  # 2 sec on + 1 sec off
    pos = elapsed_ms % cycle_ms
    if pos < 2000:
        _led.on()
    else:
        _led.off()


def status_connected():
    """Successfully connected: ON, blink 5 times, leave OFF"""
    if _led is None:
        return
    _led.on()
    time.sleep(1)
    blink(5, 150, 150)
    _led.off()
