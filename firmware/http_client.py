"""Minimal HTTPS JSON client for Pico W / Pico 2 W (no pip)."""

import json
import socket
import ssl

_ssl_context = None
_ntp_ok = False
# host -> sockaddr that last connected successfully (www.rcdrift.ro has several A records).
_preferred = {}


def _mem_pair():
    """(free, alloc) after a collect — useful in Thonny serial."""
    try:
        import gc
        gc.collect()
        return gc.mem_free(), gc.mem_alloc()
    except Exception:
        return -1, -1


def _mem_free():
    return _mem_pair()[0]


def heap_report(tag="heap"):
    """Print free/alloc and optional micropython heap dump (shows in Thonny Shell)."""
    free, alloc = _mem_pair()
    total = free + alloc if free >= 0 and alloc >= 0 else -1
    print("[HTTP] %s free=%d alloc=%d total~=%d" % (tag, free, alloc, total))
    try:
        import micropython
        micropython.mem_info(1)
    except Exception as e:
        print("[HTTP] mem_info unavailable:", type(e).__name__)
    return free, alloc


def _exc_detail(e):
    """Short exception text for serial (MicroPython args vary)."""
    try:
        parts = []
        if e.args:
            for a in e.args:
                parts.append(str(a))
        msg = " ".join(parts).strip()
        return msg if msg else type(e).__name__
    except Exception:
        return type(e).__name__


def reset_transport(keep_time=False, clear_peers=False):
    """Drop cached TLS (and optionally NTP/peers) so the next request can recover."""
    global _ssl_context, _ntp_ok, _preferred
    _ssl_context = None
    if not keep_time:
        _ntp_ok = False
    if clear_peers:
        _preferred = {}
    try:
        import gc
        gc.collect()
    except Exception:
        pass
    free, alloc = _mem_pair()
    print("[HTTP] transport reset free=%d alloc=%d keep_time=%s" % (free, alloc, keep_time))


def _fail(stage, e, dump_heap=True):
    """Raise OSError with stage + detail; always log to serial first."""
    detail = _exc_detail(e)
    free, alloc = _mem_pair()
    print("[HTTP] FAIL", stage + ":", detail, "free=%d alloc=%d" % (free, alloc))
    try:
        import time
        t = time.gmtime()
        print("[HTTP] UTC ~ %04d-%02d-%02d %02d:%02d" % (t[0], t[1], t[2], t[3], t[4]))
    except Exception:
        pass
    if dump_heap:
        try:
            heap_report("after-" + stage)
        except Exception:
            pass
    raise OSError("%s: %s" % (stage, detail))


def _ensure_time(force=False):
    """TLS needs a plausible clock; Pico W boots far in the past without NTP."""
    global _ntp_ok
    if _ntp_ok and not force:
        return
    import time
    year = time.gmtime()[0]
    print("[HTTP] NTP: syncing (RTC year=%d force=%s)…" % (year, force))
    try:
        import ntptime
        ntptime.settime()
        t = time.gmtime()
        print("[HTTP] NTP ok: %04d-%02d-%02d %02d:%02d free=%d" % (
            t[0], t[1], t[2], t[3], t[4], _mem_free()))
        _ntp_ok = True
    except Exception as e:
        print("[HTTP] NTP failed:", _exc_detail(e), "free=%d" % _mem_free())
        _ntp_ok = False


def _tls_context():
    """One shared SSLContext — building + loading the CA every request OOMs Pico W."""
    global _ssl_context
    if _ssl_context is None:
        print("[HTTP] TLS context init free=%d" % _mem_free())
        from root_ca import DER
        try:
            import gc
            gc.collect()
        except Exception:
            pass
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_verify_locations(cadata=DER)
        _ssl_context = ctx
        print("[HTTP] TLS context ready free=%d" % _mem_free())
    return _ssl_context


def _parse_url(url):
    if not url.startswith("https://"):
        raise ValueError("only https")
    rest = url[8:]
    path = "/"
    if "/" in rest:
        host, path = rest.split("/", 1)
        path = "/" + path
    else:
        host = rest
    port = 443
    if ":" in host:
        host, ps = host.split(":", 1)
        port = int(ps)
    return host, port, path


def _peer_host(addr):
    try:
        return str(addr[0])
    except Exception:
        return str(addr)


def _resolve_peers(host, port):
    """IPv4-first peer list; preferred successful peer tried first."""
    infos = []
    try:
        infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
    except Exception as e:
        print("[HTTP] AF_INET dns:", _exc_detail(e))
    if not infos:
        infos = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    peers = []
    for info in infos:
        addr = info[-1]
        if addr not in peers:
            peers.append(addr)
    pref = _preferred.get(host)
    if pref is not None:
        # Rebuild list with preferred first even if DNS order changed.
        rest = [a for a in peers if a != pref]
        peers = [pref] + rest
    return peers


def _connect_any(host, port, timeout):
    """Try every resolved address. errno 110 = ETIMEDOUT on a dead/blocked A-record."""
    global _preferred
    stage_peers = _resolve_peers(host, port)
    if not stage_peers:
        raise OSError("dns: no addresses")
    print("[HTTP] dns %s -> %d peer(s)" % (host, len(stage_peers)))
    last = None
    for addr in stage_peers:
        tip = _peer_host(addr)
        print("[HTTP] connect try %s:%s (timeout=%ss)" % (tip, port, timeout))
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect(addr)
            _preferred[host] = addr
            print("[HTTP] connected %s:%s" % (tip, port))
            return sock
        except Exception as e:
            last = e
            print("[HTTP] connect fail %s: %s" % (tip, _exc_detail(e)))
            try:
                sock.close()
            except Exception:
                pass
            if _preferred.get(host) == addr:
                _preferred.pop(host, None)
    raise OSError("connect: %s" % _exc_detail(last or OSError("all peers failed")))


def _request_once(method, url, data=None, headers=None, timeout=8):
    """Single attempt. Raises OSError on transport failure."""
    host, port, path = _parse_url(url)
    headers = dict(headers or {})
    body = b""
    if data is not None:
        if isinstance(data, (dict, list)):
            body = json.dumps(data).encode()
        elif isinstance(data, str):
            body = data.encode()
        else:
            body = data
        headers.setdefault("Content-Type", "application/json")
        headers["Content-Length"] = str(len(body))
    headers.setdefault("Host", host)
    headers.setdefault("Connection", "close")
    lines = ["%s %s HTTP/1.0" % (method, path)]
    for k, v in headers.items():
        lines.append("%s: %s" % (k, v))
    req = ("\r\n".join(lines) + "\r\n\r\n").encode() + body

    free, alloc = _mem_pair()
    print("[HTTP]", method, host + path, "free=%d alloc=%d" % (free, alloc))
    _ensure_time()
    sock = None
    buf = b""
    ssock = None
    stage = "connect"
    try:
        # Per-peer TCP timeout; multi-A hosts need room to fall through.
        connect_timeout = timeout if timeout and timeout > 4 else 8
        try:
            sock = _connect_any(host, port, connect_timeout)
        except Exception as e:
            _fail("connect", e, dump_heap=False)
        stage = "tls"
        free, alloc = _mem_pair()
        print("[HTTP] pre-tls free=%d alloc=%d" % (free, alloc))
        try:
            ssock = _tls_context().wrap_socket(sock, server_hostname=host)
        except Exception as e:
            _fail("tls", e)
        try:
            stage = "write"
            sent = 0
            while sent < len(req):
                n = ssock.write(req[sent:sent + 1024])
                if not n:
                    raise OSError("short write")
                sent += n
            stage = "read"
            ssock.settimeout(timeout if timeout else 8)
            while True:
                try:
                    chunk = ssock.read(1024)
                except Exception as e:
                    _fail("read", e)
                if not chunk:
                    break
                buf += chunk
                if len(buf) > 16384:
                    raise OSError("response too large")
        finally:
            try:
                if ssock is not None:
                    ssock.close()
            except Exception:
                pass
    finally:
        try:
            if sock is not None:
                sock.close()
        except Exception:
            pass
        try:
            import gc
            gc.collect()
        except Exception:
            pass

    if b"\r\n\r\n" not in buf:
        raise OSError("bad HTTP response (empty/truncated) stage=%s" % stage)
    head, raw = buf.split(b"\r\n\r\n", 1)
    status_line = head.split(b"\r\n", 1)[0]
    parts = status_line.split()
    status = int(parts[1]) if len(parts) >= 2 else 0
    print("[HTTP]", status, host + path, "free=%d" % _mem_free())
    lower_head = head.lower()
    if b"transfer-encoding: chunked" in lower_head:
        chunks = []
        while True:
            line, raw = raw.split(b"\r\n", 1)
            length = int(line.split(b";", 1)[0], 16)
            if length == 0:
                break
            if len(raw) < length + 2 or raw[length:length + 2] != b"\r\n":
                raise OSError("Incomplete chunk")
            chunks.append(raw[:length])
            raw = raw[length + 2:]
        raw = b"".join(chunks)
    else:
        for line in lower_head.split(b"\r\n"):
            if line.startswith(b"content-length:") and len(raw) != int(line.split(b":", 1)[1]):
                raise OSError("Incomplete body")
    try:
        text = raw.decode()
    except Exception:
        text = ""
    return status, text


def request(method, url, data=None, headers=None, timeout=8):
    """Returns (status_code, body_text). Retries once after a light transport reset."""
    try:
        return _request_once(method, url, data=data, headers=headers, timeout=timeout)
    except OSError as e:
        detail = _exc_detail(e)
        print("[HTTP] recovering:", detail)
        # Connect timeouts are network/DNS-order issues — keep NTP, reshuffle peers.
        keep_time = detail.startswith("connect:")
        reset_transport(keep_time=keep_time, clear_peers=True)
        if not keep_time:
            _ensure_time(force=True)
        try:
            import time
            time.sleep_ms(400)
        except Exception:
            pass
        print("[HTTP] retry once…")
        return _request_once(method, url, data=data, headers=headers, timeout=timeout)


def request_json(method, url, data=None, headers=None, timeout=8):
    status, text = request(method, url, data=data, headers=headers, timeout=timeout)
    parsed = None
    if text:
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
    return status, parsed
