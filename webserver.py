"""
Web server for Start Light - settings page and remote control
"""

import socket
import network
import json

# Global state - set by /start request
start_requested = False
start_delay_value = 5  # seconds, set when /start is called


def get_ip():
    """Get device IP address"""
    try:
        sta = network.WLAN(network.STA_IF)
        if sta.isconnected():
            return sta.ifconfig()[0]
    except Exception:
        pass
    return "0.0.0.0"


def parse_request(data):
    """Parse HTTP request, return (method, path, body, query)"""
    lines = data.decode().split("\r\n")
    if not lines:
        return None, None, None, {}
    parts = lines[0].split()
    if len(parts) < 2:
        return None, None, None, {}
    method, full_path = parts[0], parts[1]
    path, query = full_path, {}
    if "?" in full_path:
        path, qs = full_path.split("?", 1)
        for pair in qs.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                query[k] = v
    body = None
    for i, line in enumerate(lines[1:], 1):
        if line == "" and i + 1 < len(lines):
            body = "\r\n".join(lines[i + 1:])
            break
    return method, path, body, query


def html_escape(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _get_wifi_ssid():
    try:
        from wifi_config import load_credentials
        ssid, _ = load_credentials()
        return ssid or ""
    except Exception:
        return ""


def _get_wifi_password():
    return ""  # Never show password in HTML


def serve_settings(settings):
    """Generate settings page HTML"""
    return """<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Start Light - Settings</title>
<style>
body{font-family:sans-serif;max-width:400px;margin:20px auto;padding:10px;background:#1a1a2e;color:#eee;}
h1{color:#e94560;}
input,select,button{width:100%;padding:10px;margin:5px 0;border-radius:5px;border:1px solid #333;}
button{background:#e94560;color:#fff;border:none;cursor:pointer;font-size:16px;}
button:hover{background:#c73e54;}
a{color:#0f3460;color:#4fc3f7;}
label{display:block;margin-top:10px;}
</style></head><body>
<h1>Start Light Settings</h1>
<form method="POST" action="/settings">
<label>WiFi SSID:</label>
<input type="text" name="wifi_ssid" value=""" + html_escape(_get_wifi_ssid()) + """ placeholder="Network name">
<label>WiFi Password:</label>
<input type="password" name="wifi_password" value=""" + html_escape(_get_wifi_password()) + """ placeholder="Leave blank to keep current">
<label>Red light duration (sec):</label>
<input type="number" name="red_duration" step="0.1" value=""" + str(settings["red_duration"]) + """ min="0.5" max="5">
<label>Random wait min (sec):</label>
<input type="number" name="random_wait_min" step="0.1" value=""" + str(settings["random_wait_min"]) + """ min="0" max="10">
<label>Random wait max (sec):</label>
<input type="number" name="random_wait_max" step="0.1" value=""" + str(settings["random_wait_max"]) + """ min="0" max="10">
<label>Yellow interval (sec):</label>
<input type="number" name="yellow_interval" step="0.1" value=""" + str(settings["yellow_interval"]) + """ min="0.1" max="2">
<label>Green off delay (sec):</label>
<input type="number" name="green_off_delay" step="0.1" value=""" + str(settings["green_off_delay"]) + """ min="1" max="10">
<label>Start delay mode:</label>
<select name="start_delay_mode">
<option value="0" """ + ("selected" if settings["start_delay_mode"]==0 else "") + """>Random (5-20 sec)</option>
<option value="1" """ + ("selected" if settings["start_delay_mode"]==1 else "") + """>Fixed</option>
</select>
<label>Fixed start delay (sec) - when fixed mode:</label>
<input type="number" name="start_delay_fixed" value=""" + str(settings["start_delay_fixed"]) + """ min="1" max="60">
<label>Random delay min (sec):</label>
<input type="number" name="start_delay_random_min" value=""" + str(settings["start_delay_random_min"]) + """ min="1" max="60">
<label>Random delay max (sec):</label>
<input type="number" name="start_delay_random_max" value=""" + str(settings["start_delay_random_max"]) + """ min="1" max="60">
<button type="submit">Save Settings</button>
</form>
<h2 style="margin-top:24px;">LED test</h2>
<p style="font-size:14px;color:#aaa;">Each output stays <strong>on</strong> while checked, <strong>off</strong> when unchecked (SSR / active-low).</p>
<label style="display:flex;align-items:center;gap:8px;"><input type="checkbox" id="ledTest0" onchange="ledTest(0,this.checked)"> Red (GP2)</label>
<label style="display:flex;align-items:center;gap:8px;"><input type="checkbox" id="ledTest1" onchange="ledTest(1,this.checked)"> Yellow 1 (GP3)</label>
<label style="display:flex;align-items:center;gap:8px;"><input type="checkbox" id="ledTest2" onchange="ledTest(2,this.checked)"> Yellow 2 (GP4)</label>
<label style="display:flex;align-items:center;gap:8px;"><input type="checkbox" id="ledTest3" onchange="ledTest(3,this.checked)"> Green (GP5)</label>
<button type="button" onclick="ledTestAllOff()" style="margin-top:10px;background:#333;">All LEDs off</button>
<p id="ledTestMsg" style="font-size:13px;color:#888;"></p>
<script>
async function ledTest(n,on){
  var msg=document.getElementById('ledTestMsg');
  msg.textContent='...';
  try{
    var r=await fetch('/api/led?n='+n+'&on='+(on?1:0));
    var j=await r.json();
    msg.textContent=j.ok?'OK':'Error';
    setTimeout(function(){msg.textContent='';},1500);
  }catch(e){msg.textContent='Failed: '+e;}
}
async function ledTestAllOff(){
  for(var i=0;i<4;i++){
    document.getElementById('ledTest'+i).checked=false;
    await fetch('/api/led?n='+i+'&on=0');
  }
  var msg=document.getElementById('ledTestMsg');
  msg.textContent='All off';
  setTimeout(function(){msg.textContent='';},1500);
}
</script>
<p><a href="/">Remote Control</a></p>
</body></html>"""


def serve_control(show_saved=False):
    """Generate remote control page HTML"""
    saved_msg = '<p id="savedMsg" style="color:#4fc3f7;margin:10px;">Settings saved!</p><script>setTimeout(function(){var m=document.getElementById("savedMsg");if(m)m.style.display="none";},4000);</script>' if show_saved else ""
    return """<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Start Light - Remote</title>
<style>
body{font-family:sans-serif;text-align:center;padding:20px;background:#1a1a2e;color:#eee;}
h1{color:#e94560;}
#startBtn{width:200px;height:200px;border-radius:50%;font-size:24px;font-weight:bold;
background:#e94560;color:#fff;border:none;cursor:pointer;margin:20px;}
#startBtn:hover{background:#c73e54;}
#startBtn:disabled{background:#555;cursor:not-allowed;}
#countdown{font-size:48px;margin:20px;color:#4fc3f7;}
#status{font-size:18px;margin:10px;}
a{color:#4fc3f7;}
</style></head><body>
<h1>Start Light</h1>
""" + saved_msg + """
<div id="countdown"></div>
<div id="status">Ready</div>
<button id="startBtn" onclick="startRace()">START</button>
<p><a href="/settings">Settings</a></p>
<script>
async function startRace(){
  var btn=document.getElementById('startBtn');
  var cd=document.getElementById('countdown');
  var st=document.getElementById('status');
  btn.disabled=true;
  st.textContent='Starting...';
  try{
    var r=await fetch('/start');
    var j=await r.json();
    if(j.ok){
      st.textContent='Countdown: '+j.delay+' sec';
      for(var i=j.delay;i>=0;i--){
        cd.textContent=i;
        await new Promise(x=>setTimeout(x,1000));
      }
      cd.textContent='GO!';
      st.textContent='Race started!';
      await new Promise(x=>setTimeout(x,3000));
    }
  }catch(e){st.textContent='Error: '+e;}
  cd.textContent='';
  st.textContent='Ready';
  btn.disabled=false;
}
</script>
</body></html>"""


def _unquote(s):
    """Simple URL decode for form values"""
    if not s:
        return s
    result = []
    i = 0
    while i < len(s):
        if s[i] == "%" and i + 2 < len(s):
            try:
                result.append(chr(int(s[i + 1:i + 3], 16)))
                i += 3
            except Exception:
                result.append(s[i])
                i += 1
        else:
            result.append(" " if s[i] == "+" else s[i])
            i += 1
    return "".join(result)


def parse_form(body):
    """Parse application/x-www-form-urlencoded body"""
    if not body:
        return {}
    d = {}
    for pair in body.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            d[k] = _unquote(v)
    return d


def _safe_float(val, default):
    """Parse float, return default on error"""
    try:
        return float(val) if val else default
    except (ValueError, TypeError):
        return default


def _safe_int(val, default):
    """Parse int, return default on error"""
    try:
        return int(val) if val else default
    except (ValueError, TypeError):
        return default


def handle_request(conn, settings, light_controller):
    global start_requested
    try:
        data = conn.recv(2048)
        if not data:
            return
        # For POST, body might be split - read more if Content-Length indicates more
        for line in data.decode().split("\r\n"):
            if line.lower().startswith("content-length:"):
                try:
                    cl = int(line.split(":", 1)[1].strip())
                    sep = data.find(b"\r\n\r\n")
                    if sep >= 0:
                        needed = sep + 4 + cl
                        while len(data) < needed:
                            more = conn.recv(512)
                            if not more:
                                break
                            data += more
                except (ValueError, IndexError):
                    pass
                break
        method, path, body, query = parse_request(data)
        if not path:
            conn.close()
            return

        path = path.rstrip("/") or "/"
        print("[Web] %s %s" % (method, path))
        response = ""
        content_type = "text/html"

        if path == "/" or path == "/control":
            response = serve_control(show_saved=(query.get("saved") == "1"))
        elif path == "/settings":
            if method == "POST" and body:
                form = parse_form(body)
                if form:
                    try:
                        # WiFi credentials
                        wifi_ssid = (form.get("wifi_ssid") or "").strip()
                        wifi_pwd = (form.get("wifi_password") or "").strip()
                        if wifi_ssid:
                            from wifi_config import save_credentials, load_credentials
                            _, old_pwd = load_credentials()
                            save_credentials(wifi_ssid, wifi_pwd if wifi_pwd else (old_pwd or ""))
                        settings["red_duration"] = _safe_float(form.get("red_duration"), 1)
                        settings["random_wait_min"] = _safe_float(form.get("random_wait_min"), 1)
                        settings["random_wait_max"] = _safe_float(form.get("random_wait_max"), 3)
                        settings["yellow_interval"] = _safe_float(form.get("yellow_interval"), 0.5)
                        settings["green_off_delay"] = _safe_float(form.get("green_off_delay"), 3)
                        settings["start_delay_mode"] = _safe_int(form.get("start_delay_mode"), 0)
                        settings["start_delay_fixed"] = _safe_int(form.get("start_delay_fixed"), 5)
                        settings["start_delay_random_min"] = _safe_int(form.get("start_delay_random_min"), 5)
                        settings["start_delay_random_max"] = _safe_int(form.get("start_delay_random_max"), 20)
                        from settings import save
                        save(settings)
                        print("[Web] Settings saved, redirecting to /")
                        # Redirect to main page with success message
                        conn.send(b"HTTP/1.1 303 See Other\r\nLocation: /?saved=1\r\nConnection: close\r\n\r\n")
                        conn.close()
                        return
                    except Exception as e:
                        print("[Web] Settings save error:", e)
            response = serve_settings(settings)
        elif path == "/start":
            global start_delay_value
            from settings import get_start_delay
            delay = get_start_delay(settings)
            start_requested = True
            start_delay_value = delay
            print("[Web] Start requested, delay=%ds" % int(delay))
            content_type = "application/json"
            response = json.dumps({"ok": True, "delay": int(delay)})
        elif path == "/api/settings":
            content_type = "application/json"
            response = json.dumps(settings)
        elif path == "/api/led":
            # GET /api/led?n=0..3&on=0|1 — manual test; on=1 keeps output active (active-low)
            try:
                n = _safe_int(query.get("n"), -1)
                on = _safe_int(query.get("on"), 0)
                if 0 <= n <= 3:
                    light_controller.set_light(n, bool(on))
                    print("[Web] LED test n=%d on=%d" % (n, on))
                    content_type = "application/json"
                    response = json.dumps({"ok": True, "n": n, "on": bool(on)})
                else:
                    content_type = "application/json"
                    response = json.dumps({"ok": False, "error": "n must be 0-3"})
            except Exception as e:
                content_type = "application/json"
                response = json.dumps({"ok": False, "error": str(e)})
        else:
            response = "<h1>404</h1><p><a href='/'>Control</a> | <a href='/settings'>Settings</a></p>"

        conn.send(b"HTTP/1.1 200 OK\r\nContent-Type: " + content_type.encode() + b"\r\nConnection: close\r\n\r\n")
        conn.send(response.encode() if isinstance(response, str) else response)
    except Exception as e:
        try:
            conn.send(b"HTTP/1.1 500 OK\r\n\r\nError: " + str(e).encode())
        except Exception:
            pass
    finally:
        conn.close()


def run_server(settings, light_controller, port=80):
    """Run HTTP server - accepts one connection, handles it, returns"""
    global start_requested
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("", port))
    except OSError:
        return  # Port in use
    s.listen(1)
    s.settimeout(1.0)
    try:
        conn, addr = s.accept()
        conn.settimeout(30)  # Allow time for POST body + file save (avoid ETIMEDOUT)
        handle_request(conn, settings, light_controller)
    except OSError:
        pass  # Timeout
    finally:
        s.close()


def is_start_requested():
    global start_requested
    return start_requested


def get_start_delay_value():
    global start_delay_value
    return start_delay_value


def clear_start_requested():
    global start_requested
    start_requested = False
