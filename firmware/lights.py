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
        """Turn off all lights"""
        self.set_all_lights(False)

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
                           yellow_interval, green_off_delay, callback=None):
        """
        Run the drift/F1 style start sequence.
        start_delay: seconds to wait after button push
        callback: optional func(phase, countdown_sec) for UI updates
        """
        print("[Light] Start sequence: delay=%ds red=%.1fs rand=%.1f-%.1fs" % (start_delay, red_dur, rand_min, rand_max))
        self.all_off()

        # Phase 1: Countdown delay
        print("[Light] Phase 1: Countdown %ds" % start_delay)
        if callback:
            callback("countdown", int(start_delay))
        for sec in range(int(start_delay), 0, -1):
            if callback:
                callback("countdown", sec)
            time.sleep(1)
        if callback:
            callback("countdown", 0)

        # Phase 2: Red light
        print("[Light] Phase 2: Red light")
        self.set_light(RED, True)
        time.sleep(red_dur)

        # Phase 3: Random wait (1-3 sec typical)
        wait = random.uniform(rand_min, rand_max)
        print("[Light] Phase 3: Random wait %.1fs" % wait)
        time.sleep(wait)

        # Phase 4: Yellow 1
        print("[Light] Phase 4: Yellow 1")
        self.set_light(YELLOW1, True)
        time.sleep(yellow_interval)

        # Phase 5: Yellow 2
        print("[Light] Phase 5: Yellow 2")
        self.set_light(YELLOW2, True)
        time.sleep(yellow_interval)

        # Phase 6: Green - GO!
        print("[Light] Phase 6: GREEN - GO!")
        self.set_light(GREEN, True)
        if callback:
            callback("go", 0)
        time.sleep(green_off_delay)

        # Phase 7: All off
        print("[Light] Phase 7: All off - sequence complete")
        self.all_off()
        if callback:
            callback("done", 0)
