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


def _defaults():
    return {
        "api_base": DEFAULT_API_BASE,
        "device_id": "",
        "device_token": "",
        "device_public_id": "",
        "event_id": "",
        "enabled": False,
    }


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


def _request(method, path, body=None, token=None, timeout=8):
    cfg = load()
    base = (cfg.get("api_base") or DEFAULT_API_BASE).rstrip("/")
    url = base + path
    try:
        from http_client import request_json
        status, parsed = request_json(method, url, data=body, headers=_headers(token), timeout=timeout)
        if status < 200 or status >= 300:
            print("[Cloud] HTTP", status, path)
            return parsed
        return parsed if parsed is not None else {}
    except Exception as e:
        print("[Cloud] Request failed:", e)
        return None


def pair(code, label="Start Light", firmware_version=""):
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
        "code": str(code).strip().upper(),
        "devicePublicId": public_id,
        "label": label,
        "firmwareVersion": firmware_version or "micropython",
    }
    res = _request("POST", "/api/startlight/pair", body)
    if not res or not res.get("ok") or not res.get("deviceToken"):
        err = (res or {}).get("error") or "pair failed"
        print("[Cloud] Pair failed:", err)
        return False, err
    cfg["device_token"] = res["deviceToken"]
    cfg["device_id"] = res.get("deviceId") or ""
    cfg["event_id"] = res.get("eventId") or ""
    cfg["enabled"] = True
    if res.get("apiBase"):
        cfg["api_base"] = res["apiBase"]
    save(cfg)
    print("[Cloud] Paired to event", cfg["event_id"])
    return True, "ok"


def poll():
    """Short poll. Returns payload dict or None."""
    global _last_poll_ms
    if not is_paired():
        return None
    now = time.ticks_ms()
    if _last_poll_ms and time.ticks_diff(now, _last_poll_ms) < _POLL_INTERVAL_MS:
        return None
    _last_poll_ms = now
    cfg = load()
    return _request("GET", "/api/startlight/poll", token=cfg["device_token"], timeout=6)


def claim(command_id):
    if not is_paired():
        return None
    cfg = load()
    return _request("POST", "/api/startlight/claim", {"commandId": command_id}, token=cfg["device_token"])


def post_event(event_type, command_id=None, detail=None):
    if not is_paired():
        return None
    cfg = load()
    body = {"type": event_type, "at": "%d" % time.time()}
    if command_id:
        body["commandId"] = command_id
    if detail is not None:
        body["detail"] = detail
    return _request("POST", "/api/startlight/events", body, token=cfg["device_token"])


def status_line():
    if not is_paired():
        return "Local"
    cfg = load()
    return "Bound" if cfg.get("event_id") else "Cloud"
