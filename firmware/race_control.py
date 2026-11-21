"""Protocol 2 coordinator. Paired starts always require the current server step.

No GPIO actuation lives here: the single LightController implementation owns lamps.
"""
import time


class SequenceStopped(Exception):
    pass


class RaceCoordinator:
    def __init__(self, client, lamps, sensor_reset=None):
        self.client = client
        self.lamps = lamps
        self.sensor_reset = sensor_reset or (lambda: None)
        self.active = None
        self.revision = None
        self.last_ok = None
        self.view = None
        self.need_stop = True
        self.done_pending = False
        self.last_completed = None
        self.seen_command = None

    def _expired(self):
        return self.last_ok is None or time.ticks_diff(time.ticks_ms(), self.last_ok) > 5000

    def stop(self):
        self.lamps.all_off()
        self.sensor_reset()
        old = self.active
        self.active = None
        self.done_pending = False
        self.need_stop = True
        if self.view and self.view.get('control'):
            ok = self.client.ack_off(self.view['control']['revision'], stopped=True,
                                     aborted_command=old)
            if ok:
                self.need_stop = False

    def tick(self):
        if not self.client.is_paired():
            if self.active:
                raise SequenceStopped('Unpaired during sequence')
            return None
        payload = self.client.poll()
        if payload and (payload.get('control') or {}).get('protocol') == 2:
            self.view = payload
            self.last_ok = time.ticks_ms()
            control = payload['control']
            cue = payload.get('cue') or {}
            if self.active:
                if (not payload.get('bound') or control.get('stop') or control.get('paused')
                        or not control.get('permitted') or control['revision'] != self.revision
                        or cue.get('commandId') != self.active
                        or cue.get('status') not in ('starting', 'go', 'done', 'finished')):
                    raise SequenceStopped('Server stopped this step')
            else:
                # Idle: ack only for boot sync, orphans, or an outstanding need_stop.
                # control.stop is true all through Preparation (not permitted) — do not
                # POST TLS acks every poll or Pico W OOMs / soft-reboots and goes offline.
                self.lamps.all_off()
                orphan = cue.get('status') in ('starting', 'go')
                if self.need_stop or control.get('syncRequired') or orphan:
                    stopped = self.need_stop or orphan
                    if self.client.ack_off(control['revision'], stopped=stopped,
                                           aborted_command=cue.get('commandId') if orphan else None):
                        self.need_stop = False
                    return None
                command = payload.get('pendingCommand')
                if (command and command.get('type') == 'START' and control.get('permitted')
                        and not control.get('paused') and command.get('commandId') != self.seen_command):
                    command_id = command['commandId']
                    claimed = self.client.claim(command_id, control['revision'])
                    if claimed and claimed.get('ok') and claimed.get('claimed') is True:
                        self.active = command_id
                        self.seen_command = command_id
                        self.revision = control['revision']
                        return command_id
                    self.need_stop = True
                    self.client.ack_off(control['revision'], stopped=True,
                                        aborted_command=command_id)
        elif payload is not None:
            if self.active:
                raise SequenceStopped('Binding or protocol unavailable')
            self.need_stop = True
            self.last_ok = None
            self.view = None
            self.lamps.all_off()
        if not self.active and self._expired():
            self.need_stop = True
            self.lamps.all_off()
        if self.active and self._expired():
            raise SequenceStopped('Server lease lost')
        if self.done_pending and self.active:
            self.report('done')
        return None

    def report(self, phase):
        if not self.active:
            return False
        result = self.client.signal(phase, self.active, self.revision)
        ok = bool(result and result.get('ok') and not result.get('ignored'))
        if phase == 'go' and not ok:
            raise SequenceStopped('Green not confirmed')
        if phase == 'done':
            self.done_pending = not ok
            if ok:
                self.last_completed = (self.active, self.revision)
                self.active = None
        return ok

    def press(self):
        if not self.client.is_paired():
            return {'ok': False, 'error': 'Not paired'}
        if self._expired() or not self.view:
            return {'ok': False, 'error': 'Reconnect to RCDrift'}
        control = self.view.get('control') or {}
        if self.active or control.get('paused') or not control.get('canPress'):
            return {'ok': False, 'error': control.get('blocked') or 'Wait for the current step'}
        return self.client.press_button(control['revision'])

    def sensor_event(self, event):
        command = (self.active, self.revision) if self.active else self.last_completed
        if command:
            return self.client.signal(event, command[0], command[1])


class PhysicalButton:
    """Optional active-low button. Never fires on boot or repeats while held."""
    def __init__(self, pin=None, debounce_ms=50):
        self.pin = pin
        self.debounce_ms = debounce_ms
        self.raw = 0 if pin and not pin.value() else 1
        self.stable = self.raw
        self.changed = time.ticks_ms()
        self.released = False

    def pressed(self):
        if self.pin is None:
            return False
        value = self.pin.value()
        now = time.ticks_ms()
        if value != self.raw:
            self.raw = value
            self.changed = now
        if time.ticks_diff(now, self.changed) < self.debounce_ms:
            return False
        if value == 1:
            self.released = True
        fire = self.stable != value and value == 0 and self.released
        self.stable = value
        if fire:
            self.released = False
        return fire
