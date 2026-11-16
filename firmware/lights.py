"""
Start Light Control Module
Controls LEDs via GPIO through Solid State Relays
Single set: 4 pins drive all lights (wire multiple sets in parallel per color)
"""

import machine
import time
import random
from config import GPIO_PINS

# Light indices
RED = 0
YELLOW1 = 1
YELLOW2 = 2
GREEN = 3


class LightController:
    def __init__(self):
        self.pins = []
        self._init_pins()

    def _init_pins(self):
        """Initialize 4 GPIO pins: Red, Yellow1, Yellow2, Green"""
        self.pins = []
        for gp in GPIO_PINS:
            pin = machine.Pin(gp, machine.Pin.OUT)
            pin.value(1)  # Active-low: HIGH = lights OFF at startup
            self.pins.append(pin)
        print("[Light] GPIO %s initialized (active-low)" % str(GPIO_PINS))

    def _get_pin(self, light_idx):
        """Get pin for light index (0=Red, 1=Y1, 2=Y2, 3=Green)"""
        if 0 <= light_idx < len(self.pins):
            return self.pins[light_idx]
        return None

    def set_light(self, light_idx, state):
        """Set single light on/off. state: True=ON, False=OFF. Active-LOW: LOW=ON"""
        pin = self._get_pin(light_idx)
        if pin:
            pin.value(0 if state else 1)  # Active-low: GPIO LOW = light ON

    def set_all_lights(self, state):
        """Set all lights on/off. Active-LOW: LOW=ON"""
        for pin in self.pins:
            pin.value(0 if state else 1)  # Active-low: GPIO LOW = light ON

    def set_light_type(self, light_idx, state):
        """Set light by type (Red/Yellow1/Yellow2/Green) - same as set_light for single set"""
        self.set_light(light_idx, state)

    def all_off(self):
        """Turn off all lights (active-low: drive every pin HIGH)."""
        for pin in self.pins:
            try:
                pin.value(1)
            except Exception:
                pass

    def _sleep_s(self, seconds, tick=None):
        """Sleep in short slices so Pico W / Pico 2 W (CYW43 + USB) do not wedge.

        A single long time.sleep() / sleep_ms() can freeze the board while WiFi
        is up; 50 ms slices + machine.idle() keep the system alive. Cap 60 s.
        """
        try:
            ms = int(float(seconds) * 1000.0)
        except (TypeError, ValueError):
            ms = 0
        if ms < 0:
            ms = 0
        if ms > 60000:
            ms = 60000
        while ms > 0:
            if tick:
                tick()
            chunk = 50 if ms > 50 else ms
            time.sleep_ms(chunk)
            ms -= chunk
            try:
                machine.idle()
            except Exception:
                pass

    def run_self_test(self):
        """Boot self-test: cycle through all 4 lights in sequence"""
        self.all_off()
        time.sleep(0.2)
        for light_idx in range(len(self.pins)):
            self.set_light(light_idx, True)
            time.sleep(0.15)
        time.sleep(0.3)
        self.all_off()

    def blink_status(self, color, count, interval=0.3):
        """
        Blink status.
        color: 'green', 'yellow', 'red'
        """
        self.all_off()
        if color == 'green':
            idx = GREEN
        elif color == 'yellow':
            idx = YELLOW1
        else:
            idx = RED

        for _ in range(count):
            self.set_light(idx, True)
            time.sleep(interval)
            self.set_light(idx, False)
            time.sleep(interval)

    def run_start_sequence(self, start_delay, red_dur, rand_min, rand_max,
                           yellow_interval, green_off_delay, callback=None,
                           rand_wait=None, tick=None):
        """
        Run the drift/F1 style start sequence.
        start_delay: seconds to wait after button push
        rand_wait: if set, use this hold after red (so web UI can match); else random
        callback: optional func(phase, countdown_sec) for UI updates

        always turns lamps off in finally (crash / interrupt safe).
        """
        print("[Light] Start sequence: delay=%ds red=%.1fs rand=%.1f-%.1fs" % (
            int(start_delay), float(red_dur), float(rand_min), float(rand_max)))
        try:
            self.all_off()

            # Phase 1: Countdown delay
            print("[Light] Phase 1: Countdown %ds" % int(start_delay))
            if callback:
                callback("countdown", int(start_delay))
            for sec in range(int(start_delay), 0, -1):
                if callback:
                    callback("countdown", sec)
                self._sleep_s(1, tick)
            if callback:
                callback("countdown", 0)

            # Phase 2: Red light
            print("[Light] Phase 2: Red light")
            self.set_light(RED, True)
            self._sleep_s(red_dur, tick)

            # Phase 3: Random wait (1-3 sec typical), or fixed value from /start plan
            if rand_wait is None:
                wait = random.uniform(float(rand_min), float(rand_max))
            else:
                wait = float(rand_wait)
            print("[Light] Phase 3: Random wait %.2fs" % wait)
            self._sleep_s(wait, tick)

            # Phase 4: Yellow 1
            print("[Light] Phase 4: Yellow 1")
            self.set_light(YELLOW1, True)
            self._sleep_s(yellow_interval, tick)

            # Phase 5: Yellow 2
            print("[Light] Phase 5: Yellow 2")
            self.set_light(YELLOW2, True)
            self._sleep_s(yellow_interval, tick)

            # Phase 6: Green - GO!
            self.set_light(GREEN, True)
            print("[Light] Phase 6: GREEN on, hold %.2fs" % float(green_off_delay))
            if callback:
                callback("go", 0)
            self._sleep_s(green_off_delay, tick)

            # Phase 7: All off
            self.all_off()
            print("[Light] Phase 7: All off - sequence complete")
            if callback:
                callback("done", 0)
        finally:
            # Always dark — even if a sleep/USB/WiFi glitch aborted the sequence
            self.all_off()
            print("[Light] Pins forced OFF")
