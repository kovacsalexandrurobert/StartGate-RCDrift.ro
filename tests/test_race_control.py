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


def view(revision=1, paused=False, command=None, status='armed', stop=None, sync_required=False, permitted=None):
    if stop is None:
        stop = paused
    if permitted is None:
        permitted = not paused and not stop
    return {'bound': True, 'control': {'protocol': 2, 'revision': revision,
            'paused': paused, 'stop': stop, 'permitted': permitted,
            'syncRequired': sync_required, 'canPress': permitted and not paused},
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
        self.resume_calls = 0
    def is_paired(self):
        return True
    def poll(self):
        return self.queue.popleft() if self.queue else None
    def force_poll_soon(self):
        pass
    def resume_poll(self):
        assert all(p.value() == 1 for p in self.lamps.pins)
        self.resume_calls += 1
    def ack_off(self, revision, **kw):
        assert all(p.value() == 1 for p in self.lamps.pins)
        self.acks.append((revision, kw))
        return True
    def claim(self, command, revision, plan=None):
        self.last_plan = plan
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

    def test_claim_sends_plan_for_site_preview(self):
        plan = {'delay': 2, 'red_duration': 1.0, 'random_wait': 1.5,
                'yellow_interval': 0.5, 'green_off_delay': 3.0}
        self.c.make_plan = lambda: plan
        self.assertEqual(self.claim(), 'command-1')
        self.assertEqual(self.client.last_plan, plan)
        self.assertEqual(self.c.active_plan, plan)

    def test_pause_stops_at_green_check_not_during_countdown(self):
        # Mid-sequence ticks must not HTTPS-poll (Pico W TLS abort before red).
        # STOP/pause is observed once at report('go').
        self.assertEqual(self.claim(), 'command-1')
        self.client.queue.append(view(2, paused=True, command='command-1', status='starting'))
        with self.assertRaises(SequenceStopped):
            self.lamps.run_start_sequence(0, .1, 0, 0, .1, .1,
                callback=lambda phase, sec: self.c.report(phase) if phase in ('go', 'done') else None,
                tick=self.c.tick)
        self.assertTrue(all(p.value() == 1 for p in self.lamps.pins))
        self.c.stop()
        self.assertEqual(self.client.acks[-1][0], 2)
        self.assertFalse(self.c.press()['ok'])

    def test_sequence_survives_poll_silence_after_claim(self):
        # Old behaviour: 5 s lease loss aborted Phase 1 before red. After claim,
        # ticks hold the lease locally and do not poll until green.
        self.claim()
        self.lamps.run_start_sequence(0, .1, 0, 0, .1, .1,
            callback=lambda phase, sec: self.c.report(phase) if phase in ('go', 'done') else None,
            tick=self.c.tick)
        self.assertEqual([s[0] for s in self.client.signals], ['go', 'done'])
        self.assertIsNone(self.c.active)
        self.assertGreaterEqual(self.client.resume_calls, 1, 'poll must reopen after lamps off')

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

    def test_idle_preparation_stop_does_not_reack_every_poll(self):
        # setUp already did boot sync ack; Preparation keeps stop=true forever.
        after_boot = len(self.client.acks)
        self.assertGreaterEqual(after_boot, 1)
        self.client.queue.append(view(stop=True, sync_required=False, permitted=False))
        self.assertIsNone(self.c.tick())
        self.client.queue.append(view(stop=True, sync_required=False, permitted=False))
        self.assertIsNone(self.c.tick())
        self.assertEqual(len(self.client.acks), after_boot)

    def test_sync_required_acks_once_then_idle_stop_is_quiet(self):
        after_boot = len(self.client.acks)
        self.client.queue.append(view(stop=True, sync_required=True, permitted=False))
        self.assertIsNone(self.c.tick())
        self.assertEqual(len(self.client.acks), after_boot + 1)
        self.client.queue.append(view(stop=True, sync_required=False, permitted=False))
        self.assertIsNone(self.c.tick())
        self.assertEqual(len(self.client.acks), after_boot + 1)

    def test_sync_required_with_pending_start_claims_before_ack(self):
        after_boot = len(self.client.acks)
        self.client.queue.append(view(2, sync_required=True, command='cmd-sync-start', status='armed'))
        self.assertEqual(self.c.tick(), 'cmd-sync-start')
        # Claim wins; sync ack is deferred so a slow TLS ack cannot expire START.
        self.assertEqual(len(self.client.acks), after_boot)

    def test_sync_then_followup_poll_claims_pending_start(self):
        # Site pattern: first poll sync-only, START appears on the next poll.
        after_boot = len(self.client.acks)
        self.client.queue.append(view(2, sync_required=True, permitted=True, stop=False))
        self.client.queue.append(view(2, sync_required=False, command='cmd-after-sync', status='armed'))
        self.assertEqual(self.c.tick(), 'cmd-after-sync')
        self.assertEqual(len(self.client.acks), after_boot + 1)

    def test_active_stop_still_aborts_at_green(self):
        self.assertEqual(self.claim(), 'command-1')
        self.client.queue.append(view(2, stop=True, permitted=False, command='command-1', status='starting'))
        with self.assertRaises(SequenceStopped):
            self.c.report('go')
        # Idle ticks after claim must not poll / must not raise on silence.
        self.assertIsNone(self.c.tick())


if __name__ == '__main__':
    unittest.main()
