"""
Anonymous IR break-beam finish sensor (phase 4).
After green: first break = exit, second break (after min time) = finish.
No car identity. Works in standalone and cloud modes.
"""

import time

_STATE_IDLE = "idle"
_STATE_EXPECT_EXIT = "expect_exit"
_STATE_EXPECT_FINISH = "expect_finish"
_STATE_FINISHED = "finished"

_state = _STATE_IDLE
_go_ms = 0
_pin = None
_last_level = 1
_last_edge_ms = 0
_callback = None


def configure(pin_num=None, enabled=False):
    """Attach GPIO for active-low break-beam. enabled=False keeps idle."""
    global _pin, _state, _last_level
    _state = _STATE_IDLE
    _pin = None
    if not enabled or pin_num is None:
        return
    try:
        from machine import Pin
        _pin = Pin(int(pin_num), Pin.IN, Pin.PULL_UP)
        _last_level = _pin.value()
        print("[Sensor] IR beam on GP%d" % int(pin_num))
    except Exception as e:
        print("[Sensor] Init failed:", e)
        _pin = None


def set_callback(cb):
    """cb(event) with event in ('exit','finish')."""
    global _callback
    _callback = cb


def on_go():
    """Arm after green light."""
    global _state, _go_ms
    if _pin is None:
        return
    _state = _STATE_EXPECT_EXIT
    _go_ms = time.ticks_ms()
    print("[Sensor] Armed expect_exit")


def reset():
    global _state
    _state = _STATE_IDLE


def status():
    return _state


def _min_ms():
    try:
        from config import FINISH_MIN_RUN_S
        return int(float(FINISH_MIN_RUN_S) * 1000)
    except Exception:
        return 8000


def _debounce_ms():
    try:
        from config import FINISH_DEBOUNCE_MS
        return int(FINISH_DEBOUNCE_MS)
    except Exception:
        return 40


def tick():
    """Call from ready loop. Detects active-low breaks."""
    global _state, _last_level, _last_edge_ms
    if _pin is None or _state in (_STATE_IDLE, _STATE_FINISHED):
        return None
    try:
        level = _pin.value()
    except Exception:
        return None
    now = time.ticks_ms()
    event = None
    # Falling edge = beam broken (active-low)
    if _last_level == 1 and level == 0:
        if time.ticks_diff(now, _last_edge_ms) >= _debounce_ms():
            _last_edge_ms = now
            if _state == _STATE_EXPECT_EXIT:
                _state = _STATE_EXPECT_FINISH
                event = "exit"
                print("[Sensor] Exit (break #1)")
            elif _state == _STATE_EXPECT_FINISH:
                if time.ticks_diff(now, _go_ms) >= _min_ms():
                    _state = _STATE_FINISHED
                    event = "finish"
                    print("[Sensor] Finish (break #2)")
    _last_level = level
    if event and _callback:
        try:
            _callback(event)
        except Exception as e:
            print("[Sensor] Callback failed:", e)
    return event
