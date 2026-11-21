"""Minimal HTTPS JSON client for Pico W / Pico 2 W (no pip)."""

import json
import socket
import ssl

_ssl_context = None
_ntp_ok = False


def _mem_free():
    try:
        import gc
        return gc.mem_free()
    except Exception:
        return -1


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


def _fail(stage, e):
    """Raise OSError with stage + detail; always log to serial first."""
    detail = _exc_detail(e)
    print("[HTTP] FAIL", stage + ":", detail, "mem=%d" % _mem_free())
    try:
        import time
        t = time.gmtime()
        print("[HTTP] UTC ~ %04d-%02d-%02d %02d:%02d" % (t[0], t[1], t[2], t[3], t[4]))
    except Exception:
        pass
    raise OSError("%s: %s" % (stage, detail))


def _ensure_time():
    """TLS needs a plausible clock; Pico W boots far in the past without NTP."""
    global _ntp_ok
    if _ntp_ok:
        return
    import time
    year = time.gmtime()[0]
    # Refresh whenever the RTC looks wrong for current LE certs.
    if year >= 2025 and year <= 2035:
        _ntp_ok = True
        return
    print("[HTTP] NTP: RTC year=%d, syncing…" % year)
    try:
        import ntptime
        ntptime.settime()
        t = time.gmtime()
        print("[HTTP] NTP ok: %04d-%02d-%02d %02d:%02d mem=%d" % (
            t[0], t[1], t[2], t[3], t[4], _mem_free()))
        _ntp_ok = True
    except Exception as e:
        print("[HTTP] NTP failed:", _exc_detail(e), "mem=%d" % _mem_free())


def _tls_context():
    """One shared SSLContext — building + loading the CA every request OOMs Pico W."""
    global _ssl_context
    if _ssl_context is None:
        print("[HTTP] TLS context init mem=%d" % _mem_free())
        from root_ca import DER
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_verify_locations(cadata=DER)
        _ssl_context = ctx
        print("[HTTP] TLS context ready mem=%d" % _mem_free())
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


def request(method, url, data=None, headers=None, timeout=8):
    """Returns (status_code, body_text) or raises."""
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

    print("[HTTP]", method, host + path, "mem=%d" % _mem_free())
    stage = "dns"
    try:
        addr = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)[0][-1]
    except Exception as e:
        _fail("dns", e)
    sock = socket.socket()
    sock.settimeout(timeout)
    buf = b""
    ssock = None
    try:
        stage = "connect"
        try:
            sock.connect(addr)
        except Exception as e:
            _fail("connect", e)
        stage = "ntp"
        _ensure_time()
        stage = "tls"
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
    print("[HTTP]", status, host + path, "mem=%d" % _mem_free())
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


def request_json(method, url, data=None, headers=None, timeout=8):
    status, text = request(method, url, data=data, headers=headers, timeout=timeout)
    parsed = None
    if text:
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
    return status, parsed
