"""
WiFi credential storage - separate from main config for security.
Supports multiple networks; reconnects to last successful when in range.
"""

import json
import os

CREDENTIALS_FILE = "wifi_creds.json"
NETWORKS_FILE = "wifi_networks.json"
LAST_WIFI_FILE = "last_wifi.json"
PENDING_IP_FLAG_FILE = "ble_pending_ip.json"
WIFI_COUNTRY_FILE = "wifi_country.json"


def _load_networks():
    """Load list of known networks. Migrate from wifi_creds if needed."""
    try:
        with open(NETWORKS_FILE, "r") as f:
            data = json.load(f)
            nets = data.get("networks", data) if isinstance(data, dict) else data
            if isinstance(nets, list) and nets:
                return nets
    except (OSError, ValueError):
        pass
    # Migrate from legacy wifi_creds.json
    try:
        with open(CREDENTIALS_FILE, "r") as f:
            d = json.load(f)
            ssid = d.get("ssid", "")
            pwd = d.get("password", "")
            if ssid:
                nets = [{"ssid": ssid, "password": pwd}]
                _save_networks(nets)
                print("[WiFi] Migrated from %s to %s" % (CREDENTIALS_FILE, NETWORKS_FILE))
                return nets
    except (OSError, ValueError):
        pass
    try:
        from config import WIFI_SSID, WIFI_PASSWORD
        if WIFI_SSID:
            return [{"ssid": WIFI_SSID, "password": WIFI_PASSWORD or ""}]
    except Exception:
        pass
    return []


def _save_networks(networks):
    """Save networks list to JSON"""
    with open(NETWORKS_FILE, "w") as f:
        json.dump({"networks": networks}, f)


def get_last_successful_ssid():
    """Get last successfully connected SSID"""
    try:
        with open(LAST_WIFI_FILE, "r") as f:
            return json.load(f).get("ssid", "")
    except (OSError, ValueError):
        return ""


def record_successful_connection(ssid):
    """Save SSID as last successful connection"""
    try:
        with open(LAST_WIFI_FILE, "w") as f:
            json.dump({"ssid": ssid}, f)
        print("[WiFi] Saved last successful: %s" % (ssid[:20] if ssid else ""))
    except Exception as e:
        print("[WiFi] Failed to save last:", e)


def get_networks_to_try(scan_results=None):
    """
    Return list of (ssid, password) to try, with last successful first if in range.
    scan_results: list from wlan.scan() - (ssid, bssid, channel, rssi, authmode, hidden)
    """
    networks = _load_networks()
    if not networks:
        return []
    last = get_last_successful_ssid()
    # Build list of (ssid, password)
    net_list = [(n["ssid"], n.get("password", "")) for n in networks if n.get("ssid")]

    if not last:
        return net_list

    # If last successful is in our list and (optionally) in scan, put it first
    last_in_list = [(s, p) for s, p in net_list if s == last]
    others = [(s, p) for s, p in net_list if s != last]

    if scan_results is not None:
        scan_ssids = [r[0].decode() if isinstance(r[0], bytes) else str(r[0]) for r in scan_results]
        if last in scan_ssids and last_in_list:
            return last_in_list + others
    # No scan or last not in range: still try last first
    if last_in_list:
        return last_in_list + others
    return net_list


def load_credentials():
    """Load primary credentials (first network). Returns (ssid, password) or (None, None)"""
    nets = get_networks_to_try()
    if nets:
        return nets[0]
    return None, None


def save_credentials(ssid, password):
    """Save/add WiFi credentials. Updates or appends to networks list."""
    networks = _load_networks()
    # Update existing or append
    found = False
    for n in networks:
        if n.get("ssid") == ssid:
            n["password"] = password
            found = True
            break
    if not found:
        networks.append({"ssid": ssid, "password": password})
    _save_networks(networks)
    # Also keep legacy file for compatibility
    try:
        with open(CREDENTIALS_FILE, "w") as f:
            json.dump({"ssid": ssid, "password": password}, f)
    except Exception:
        pass


def set_pending_ip_via_ble(pending):
    """Set flag: after WiFi connects, send IP via BLE to whoever sent credentials"""
    try:
        with open(PENDING_IP_FLAG_FILE, "w") as f:
            json.dump({"pending": bool(pending)}, f)
    except Exception:
        pass


def get_pending_ip_via_ble():
    """Check if we should send IP via BLE after WiFi connects"""
    try:
        with open(PENDING_IP_FLAG_FILE, "r") as f:
            return json.load(f).get("pending", False)
    except (OSError, ValueError):
        return False


def has_credentials():
    """Check if credentials are stored"""
    ssid, _ = load_credentials()
    return ssid and len(ssid) > 0


def get_wifi_country():
    """Get WiFi country code. Returns stored value from BLE or config default."""
    try:
        with open(WIFI_COUNTRY_FILE, "r") as f:
            c = json.load(f).get("country", "")
            if c and len(c) == 2:
                return c.upper()
    except (OSError, ValueError):
        pass
    try:
        from config import WIFI_COUNTRY
        return WIFI_COUNTRY or "RO"
    except Exception:
        return "RO"


def save_wifi_country(country):
    """Save WiFi country code (e.g. from BLE). 2-letter ISO code."""
    if not country or len(str(country).strip()) != 2:
        return
    try:
        c = str(country).strip().upper()
        with open(WIFI_COUNTRY_FILE, "w") as f:
            json.dump({"country": c}, f)
        print("[WiFi] Country saved: %s" % c)
    except Exception as e:
        print("[WiFi] Failed to save country:", e)
