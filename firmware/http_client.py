"""Minimal HTTPS JSON client for Pico W / Pico 2 W (no pip)."""

import json
import socket
import ssl

_ssl_context = None


def _tls_context():
    """One shared SSLContext — building + loading the CA every request OOMs Pico W."""
    global _ssl_context
    if _ssl_context is None:
        from root_ca import DER
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_verify_locations(cadata=DER)
        _ssl_context = ctx
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

    print("[HTTP]", method, host)
    try:
        addr = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)[0][-1]
    except Exception as e:
        raise OSError("DNS failed: %s" % type(e).__name__)
    sock = socket.socket()
    sock.settimeout(timeout)
    buf = b""
    try:
        sock.connect(addr)
        import time
        if time.gmtime()[0] < 2025:
            try:
                import ntptime
                ntptime.settime()
            except Exception as e:
                print("[HTTP] NTP skipped:", type(e).__name__)
        ssock = _tls_context().wrap_socket(sock, server_hostname=host)
        try:
            sent = 0
            while sent < len(req):
                n = ssock.write(req[sent:sent + 1024])
                if not n:
                    raise OSError("Incomplete HTTPS request")
                sent += n
            while True:
                try:
                    chunk = ssock.read(1024)
                except Exception:
                    raise OSError("Incomplete HTTPS response")
                if not chunk:
                    break
                buf += chunk
                if len(buf) > 16384:
                    raise OSError("HTTPS response too large")
        finally:
            try:
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
        raise OSError("bad HTTP response")
    head, raw = buf.split(b"\r\n\r\n", 1)
    status_line = head.split(b"\r\n", 1)[0]
    parts = status_line.split()
    status = int(parts[1]) if len(parts) >= 2 else 0
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
