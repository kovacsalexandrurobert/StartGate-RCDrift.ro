"""
Optional rcdrift.ro cloud client. Off until paired — standalone starts always work.
Uses short HTTPS poll (~1 s). Store credentials in cloud_creds.json (gitignored).
"""

import json
import time

CLOUD_FILE = "cloud_creds.json"
DEFAULT_API_BASE = "https://staging.rcdrift.ro"
_POLL_INTERVAL_MS = 1000
_last_poll_ms = 0
_cached = None
_boot = None
_pending_press = None
_last_payload = None
_last_status = 0
_coordinator = None


def _defaults():
    return {
        "api_base": DEFAULT_API_BASE,
        "device_id": "",
        "device_token": "",
        "device_public_id": "",
        "event_id": "",
        "enabled": False,
    }


def usable_api_base(base):
    """Accept only a public https://hostname origin (no path/port/IP). Local check only."""
    if not base or not isinstance(base, str):
        return False
    base = base.strip().rstrip("/")
    if not base.startswith("https://") or " " in base or len(base) > 96:
        return False
    host = base[8:].lower()
    # Entire remainder must be the host — reject paths/query/userinfo.
    if not host or "/" in host or "?" in host or "#" in host or "@" in host:
        return False
    if ":" in host or host.startswith(".") or host.endswith("."):
        return False
    if host == "localhost" or host.endswith(".local"):
        return False
    # Require a DNS hostname (at least one letter) so IPv4 literals like
    # 127.0.0.2 / 192.168.1.1 cannot overwrite a working public URL.
    has_letter = False
    for ch in host:
        if "a" <= ch <= "z":
            has_letter = True
        elif not (("0" <= ch <= "9") or ch in ".-"):
            return False
    return has_letter


def load():
    global _cached
    if _cached is not None:
        return _cached
    cfg = _defaults()
    try:
        with open(CLOUD_FILE) as f:
            data = json.load(f)
        if isinstance(data, dict):
            for k in cfg:
                if k in data:
                    cfg[k] = data[k]
    except Exception:
        pass
    _cached = cfg
    return cfg


def save(cfg):
    global _cached
    _cached = cfg
    try:
        with open(CLOUD_FILE, "w") as f:
            json.dump(cfg, f)
    except Exception as e:
        print("[Cloud] Save failed:", e)


def is_paired():
    cfg = load()
    return bool(cfg.get("enabled") and cfg.get("device_token"))


def unpair():
    reset_runtime()
    cfg = load()
    cfg["device_token"] = ""
    cfg["device_id"] = ""
    cfg["event_id"] = ""
    cfg["enabled"] = False
    save(cfg)
    print("[Cloud] Unpaired — standalone mode")


def _headers(token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer %s" % token
    return h


def _request(method, path, body=None, token=None, timeout=2):
    global _last_status
    cfg = load()
    base = (cfg.get("api_base") or DEFAULT_API_BASE).rstrip("/")
    url = base + path
    try:
        from http_client import request_json
        status, parsed = request_json(method, url, data=body, headers=_headers(token), timeout=timeout)
        _last_status = status
        if status < 200 or status >= 300:
            err = ""
            if isinstance(parsed, dict) and parsed.get("error"):
                err = " " + str(parsed.get("error"))[:80]
            print("[Cloud] HTTP", status, path + err)
            return parsed
        return parsed if parsed is not None else {}
    except Exception as e:
        _last_status = 0
        detail = ""
        try:
            if e.args:
                detail = " " + " ".join(str(a) for a in e.args)[:120]
        except Exception:
            pass
        mem = ""
        try:
            import gc
            mem = " mem=%d" % gc.mem_free()
        except Exception:
            pass
        print("[Cloud] Request failed:", type(e).__name__ + detail + mem)
        return None


def pair(code, label="Start Light", firmware_version=""):
    code = str(code or "").strip().upper()
    if not code or len(code) > 16:
        return False, "missing code"
    cfg = load()
    public_id = cfg.get("device_public_id") or ""
    if not public_id:
        try:
            import machine
            public_id = "pico-%s" % "".join("%02x" % b for b in machine.unique_id())
        except Exception:
            public_id = "pico-%d" % time.ticks_ms()
        cfg["device_public_id"] = public_id
    body = {
        "code": code,
        "devicePublicId": public_id,
        "label": label,
        "firmwareVersion": firmware_version or "startlight-control-2",
        "protocolVersion": 2,
    }
    print("[Cloud] Pair POST", (cfg.get("api_base") or DEFAULT_API_BASE))
    res = _request("POST", "/api/startlight/pair", body, timeout=4)
    if not res or not res.get("ok") or not res.get("deviceToken"):
        err = (res or {}).get("error") or "pair failed"
        print("[Cloud] Pair failed:", err)
        return False, err
    cfg["device_token"] = res["deviceToken"]
    cfg["device_id"] = res.get("deviceId") or ""
    cfg["event_id"] = res.get("eventId") or ""
    cfg["enabled"] = True
    # Keep the URL that successfully paired if the site returns a loopback/proxy origin.
    suggested = (res.get("apiBase") or "").strip().rstrip("/")
    if suggested:
        if usable_api_base(suggested):
            cfg["api_base"] = suggested
        else:
            print("[Cloud] Ignoring apiBase from pair:", suggested)
    reset_runtime()
    save(cfg)
    try:
        with open("cloud_state.json", "w") as f:
            json.dump({"boot_counter": 0}, f)
    except Exception as e:
        print("[Cloud] State save failed:", e)
    print("[Cloud] Paired")
    return True, "ok"



def identity():
    global _boot
    if _boot is not None:
        return _boot
    import os
    try:
        with open("cloud_state.json") as f:
            previous = json.load(f).get("boot_counter", 0)
    except OSError:
        previous = 0
    if not isinstance(previous, int) or previous < 0:
        raise ValueError("Invalid Pico boot counter")
    counter = previous + 1
    with open("cloud_state.json", "w") as f:
        json.dump({"boot_counter": counter}, f)
    boot_id = "".join("%02x" % b for b in os.urandom(16))
    _boot = {"bootId": boot_id, "bootCounter": counter}
    return _boot


def poll():
    global _last_poll_ms, _last_payload
    if not is_paired():
        return None
    now = time.ticks_ms()
    if _last_poll_ms and time.ticks_diff(now, _last_poll_ms) < _POLL_INTERVAL_MS:
        return None
    _last_poll_ms = now
    cfg = load()
    result = _request("GET", "/api/startlight/poll?bootId=" + identity()["bootId"],
                      token=cfg["device_token"], timeout=1.5)
    if result:
        _last_payload = result
    return result


def claim(command_id, revision):
    if not is_paired():
        return None
    body = dict(identity())
    body.update({"commandId": command_id, "revision": revision})
    return _request("POST", "/api/startlight/claim", body,
                    token=load()["device_token"], timeout=1.5)


def signal(event_type, command_id, revision):
    if not is_paired():
        return None
    body = dict(identity())
    body.update({"type": event_type, "commandId": command_id,
                 "revision": revision, "protocol": 2})
    return _request("POST", "/api/startlight/events", body,
                    token=load()["device_token"], timeout=1.5)


def ack_off(revision, stopped=False, aborted_command=None):
    if not is_paired():
        return False
    body = dict(identity())
    body.update({"type": "stopped" if stopped else "sync", "revision": revision,
                 "protocol": 2, "lampsOff": True})
    if aborted_command:
        body["abortedCommandId"] = aborted_command
    result = _request("POST", "/api/startlight/events", body,
                      token=load()["device_token"], timeout=1.5)
    return bool(result and result.get("ok"))


def press_button(revision):
    global _pending_press
    if not is_paired():
        return {"ok": False, "error": "Not paired"}
    if _pending_press is None:
        import os
        _pending_press = dict(identity())
        _pending_press.update({"revision": revision,
                              "requestId": "".join("%02x" % b for b in os.urandom(16))})
    result = _request("POST", "/api/startlight/button", _pending_press,
                      token=load()["device_token"], timeout=2)
    if result and result.get("ok") or _last_status in (400, 401, 403, 404, 409):
        _pending_press = None
    return result or {"ok": False, "error": "No confirmation. Press again to check the same command."}


def set_coordinator(coordinator):
    global _coordinator
    _coordinator = coordinator


def local_press():
    if _coordinator is None:
        return {"ok": False, "error": "Wait for RCDrift synchronisation"}
    return _coordinator.press()


def status_snapshot():
    control = ((_last_payload or {}).get("control") or {})
    online = _coordinator is not None and not _coordinator._expired()
    return {"paired": is_paired(), "label": control.get("label", "RCDrift"), "labelEn": control.get("labelEn", "RCDrift"),
            "blocked": control.get("blocked", ""), "blockedEn": control.get("blockedEn", ""), "paused": control.get("paused", False),
            "canPress": bool(control.get("canPress")) and online and not _coordinator.active}


def post_event(event_type, command_id=None, detail=None):
    control = ((_last_payload or {}).get("control") or {})
    if event_type == "local_start":
        return local_press()
    return signal(event_type, command_id, control.get("revision", -1))


def status_line():
    return "RCDrift" if is_paired() else "Local"


def reset_runtime():
    global _boot, _pending_press, _last_payload, _last_poll_ms
    _boot = None
    _pending_press = None
    _last_payload = None
    _last_poll_ms = 0
    if _coordinator is not None:
        _coordinator.lamps.all_off()
        _coordinator.sensor_reset()
        _coordinator.active = None
        _coordinator.view = None
        _coordinator.last_ok = None
        _coordinator.need_stop = True
        _coordinator.done_pending = False
