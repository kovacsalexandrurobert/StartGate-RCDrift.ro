import unittest
import sys
import types
import time
from pathlib import Path
from collections import deque

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'firmware'))
clock = [0]
time.ticks_ms = lambda: clock[0]
time.ticks_diff = lambda a, b: a-b
time.sleep_ms = lambda ms: clock.__setitem__(0, clock[0]+ms)


class Pin:
    OUT = 1
    IN = 0
    PULL_UP = 2
    def __init__(self, *args):
        self.level = 1
    def value(self, value=None):
        if value is not None:
            self.level = value
        return self.level


sys.modules['machine'] = types.SimpleNamespace(Pin=Pin, idle=lambda: None)
from race_control import RaceCoordinator, SequenceStopped, PhysicalButton
from lights import LightController


def view(revision=1, paused=False, command=None, status='armed'):
    return {'bound': True, 'control': {'protocol': 2, 'revision': revision,
            'paused': paused, 'stop': paused, 'permitted': not paused,
            'syncRequired': False, 'canPress': not paused},
            'cue': {'commandId': command, 'status': status} if command else None,
            'pendingCommand': {'commandId': command, 'type': 'START'} if command and status == 'armed' else None}


class Client:
    def __init__(self, lamps):
        self.queue = deque()
        self.lamps = lamps
        self.claimed = True
        self.signals = []
        self.acks = []
        self.green_ok = True
    def is_paired(self):
        return True
    def poll(self):
        return self.queue.popleft() if self.queue else None
    def ack_off(self, revision, **kw):
        assert all(p.value() == 1 for p in self.lamps.pins)
        self.acks.append((revision, kw))
        return True
    def claim(self, command, revision):
        return {'ok': True, 'claimed': self.claimed}
    def signal(self, event, command, revision):
        if event == 'done':
            assert all(p.value() == 1 for p in self.lamps.pins)
        self.signals.append((event, command, revision))
        return {'ok': self.green_ok if event == 'go' else True}
    def press_button(self, revision):
        return {'ok': True, 'revision': revision}


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        clock[0] = 0
        self.lamps = LightController()
        self.client = Client(self.lamps)
        self.c = RaceCoordinator(self.client, self.lamps)
        self.client.queue.append(view())
        self.c.tick()  # first boot stops/acknowledges, never starts

    def claim(self):
        self.client.queue.append(view(command='command-1'))
        return self.c.tick()

    def test_claim_replay_never_runs_again(self):
        self.client.claimed = False
        self.assertIsNone(self.claim())
        self.assertIsNone(self.c.active)
        self.assertTrue(all(p.value() == 1 for p in self.lamps.pins))

    def test_pause_interrupts_the_real_sequence_and_acknowledges_after_off(self):
        self.assertEqual(self.claim(), 'command-1')
        def tick():
            if clock[0] >= 100:
                self.client.queue.append(view(2, paused=True))
            self.c.tick()
        with self.assertRaises(SequenceStopped):
            self.lamps.run_start_sequence(0, 1, 0, 0, .1, .1, tick=tick)
        self.assertTrue(all(p.value() == 1 for p in self.lamps.pins))
        self.c.stop()
        self.assertEqual(self.client.acks[-1][0], 2)
        self.assertFalse(self.c.press()['ok'])

    def test_connection_loss_stops_before_green(self):
        self.claim()
        with self.assertRaises(SequenceStopped):
            self.lamps.run_start_sequence(10, 1, 0, 0, .1, .1, tick=self.c.tick)
        self.assertTrue(all(p.value() == 1 for p in self.lamps.pins))
        self.assertLessEqual(clock[0], 5050)

    def test_done_is_reported_only_after_every_lamp_is_off(self):
        self.claim()
        self.lamps.run_start_sequence(0, .1, 0, 0, .1, .1,
            callback=lambda phase, sec: self.c.report(phase) if phase in ('go', 'done') else None,
            tick=self.c.tick)
        self.assertEqual([s[0] for s in self.client.signals], ['go', 'done'])
        self.assertIsNone(self.c.active)

    def test_unconfirmed_green_fails_closed(self):
        self.claim()
        self.client.green_ok = False
        with self.assertRaises(SequenceStopped):
            self.lamps.run_start_sequence(0, .1, 0, 0, .1, .1,
                callback=lambda phase, sec: self.c.report(phase) if phase in ('go', 'done') else None,
                tick=self.c.tick)
        self.assertTrue(all(p.value() == 1 for p in self.lamps.pins))

    def test_stale_cached_page_cannot_press_after_lost_connection(self):
        clock[0] = 6000
        self.c.tick()
        self.assertFalse(self.c.press()['ok'])
        self.client.queue.append({'bound': False, 'control': None})
        self.c.tick()
        self.assertFalse(self.c.press()['ok'])

    def test_gpio_requires_release_and_debounces_without_hold_repeat(self):
        pin = Pin()
        pin.value(0)
        button = PhysicalButton(pin)
        clock[0] += 100
        self.assertFalse(button.pressed(), 'held during boot')
        pin.value(1); button.pressed(); clock[0] += 60; button.pressed()
        pin.value(0); self.assertFalse(button.pressed()); clock[0] += 60
        self.assertTrue(button.pressed()); self.assertFalse(button.pressed())
        clock[0] += 1000; self.assertFalse(button.pressed())


if __name__ == '__main__':
    unittest.main()
