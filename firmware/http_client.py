"""Minimal HTTPS JSON client for Pico W / Pico 2 W (no pip)."""

import json
import socket
import ssl


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

    addr = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)[0][-1]
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        sock.connect(addr)
        ssock = ssl.wrap_socket(sock, server_hostname=host)
        try:
            ssock.write(req)
            buf = b""
            while True:
                try:
                    chunk = ssock.read(1024)
                except Exception:
                    break
                if not chunk:
                    break
                buf += chunk
                if len(buf) > 65536:
                    break
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

    if b"\r\n\r\n" not in buf:
        raise OSError("bad HTTP response")
    head, raw = buf.split(b"\r\n\r\n", 1)
    status_line = head.split(b"\r\n", 1)[0]
    parts = status_line.split()
    status = int(parts[1]) if len(parts) >= 2 else 0
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
