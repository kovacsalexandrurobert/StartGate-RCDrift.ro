"""
Web server for Start Light - settings page and remote control
"""

import socket
import network
import json

# Global state - set by /start request
start_requested = False
start_delay_value = 5  # seconds (legacy); prefer start_plan
start_plan = None  # timing plan shared with lamps + web viz


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


def _expected_pin(settings):
    return str((settings or {}).get("web_pin") or "9009")


def _parse_cookies(raw):
    """Parse Cookie header from raw HTTP request bytes/str."""
    if isinstance(raw, bytes):
        try:
            text = raw.decode()
        except Exception:
            return {}
    else:
        text = raw
    out = {}
    for line in text.split("\r\n"):
        if line.lower().startswith("cookie:"):
            for part in line.split(":", 1)[1].split(";"):
                part = part.strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    val = v.strip().replace("%3D", "=").replace("%3A", ":")
                    out[k.strip()] = val
            break
    return out


def _pin_unlocked(settings, cookies):
    return cookies.get("sl_pin") == _expected_pin(settings)


def _send_all(conn, data):
    """Send every byte. Pico/MicroPython socket.send() often writes only a prefix.

    There is no separate HTTP payload cap to raise — callers must loop until
    the full body is written (and keep pages small enough for RAM).
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    sent = 0
    length = len(data)
    while sent < length:
        # 1 KiB chunks keep peak alloc modest on Pico 2 W / Pico W
        n = conn.send(data[sent:sent + 1024])
        if not n:
            raise OSError("socket send returned 0")
        sent += n


def _css():
    """Shared UI — visual tokens aligned with www.rcdrift.ro (compact for Pico RAM)."""
    return (
        ":root{--bg:#0a0910;--panel:#13111d;--panel2:#181522;--border:#292432;"
        "--muted:#a29cab;--pink:#f34ebc;--purple:#a47bfa;--blue:#48ccfa;"
        "--white:#f6f3fb;--lime:#c5ff63;color-scheme:dark}"
        "*{box-sizing:border-box}"
        "body{margin:0;background:var(--bg);color:var(--white);"
        "font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;"
        "-webkit-font-smoothing:antialiased}"
        ".topline{border-bottom:1px solid var(--border);padding:8px 16px;"
        "font-size:11px;font-weight:700;letter-spacing:.04em;color:var(--muted);"
        "display:flex;justify-content:space-between;gap:12px;align-items:center}"
        ".topline i{display:inline-block;width:7px;height:7px;border-radius:50%;"
        "background:var(--lime);margin-right:8px;vertical-align:middle}"
        ".lang-switch{display:inline-flex;gap:0;border:1px solid var(--border)}"
        ".lang-switch button{background:transparent;border:0;color:var(--muted);"
        "font:inherit;font-size:11px;font-weight:750;padding:6px 10px;cursor:pointer}"
        ".lang-switch button[aria-pressed=true]{background:var(--panel2);color:var(--white)}"
        ".wrap{max-width:440px;margin:0 auto;padding:18px 16px 40px}"
        ".brand{display:inline-flex;align-items:baseline;font-style:italic;"
        "font-weight:950;font-size:28px;letter-spacing:-1.4px;line-height:1;"
        "text-decoration:none;color:var(--white)}"
        ".brand .sl{color:var(--blue);letter-spacing:-8px;margin-right:12px;"
        "font-size:34px;transform:skew(-14deg);text-shadow:4px 0 0 var(--pink)}"
        ".brand .hi{color:var(--pink)}"
        ".brand small{color:#aea4bd;font-size:17px;font-weight:700;letter-spacing:-1px}"
        ".powered{margin:8px 0 0;font-size:11px;font-weight:750;letter-spacing:.08em;"
        "text-transform:uppercase;color:var(--muted)}"
        ".powered a{color:var(--blue);text-decoration:none}"
        ".bar{display:flex;align-items:center;justify-content:space-between;"
        "gap:12px;margin:16px 0 8px;flex-wrap:wrap}"
        "nav{display:flex;gap:14px;font-size:12px;font-weight:700}"
        "nav a{color:var(--muted);text-decoration:none;padding-bottom:4px;"
        "border-bottom:2px solid transparent}"
        "nav a.on{color:var(--white);border-color:var(--pink)}"
        "h1{font-style:italic;font-weight:950;letter-spacing:-2px;line-height:.95;"
        "font-size:clamp(42px,12vw,58px);margin:18px 0 8px}"
        "h1 em{color:var(--pink);font-style:italic}"
        ".lead{color:var(--muted);margin:0 0 22px;max-width:28rem}"
        ".panel{background:var(--panel);border:1px solid var(--border);padding:16px;"
        "margin:0 0 16px}"
        ".panel h2{margin:0 0 10px;font-size:12px;letter-spacing:.08em;"
        "text-transform:uppercase;color:var(--muted);font-weight:750}"
        "label{display:block;margin:12px 0 4px;font-size:12px;font-weight:700;"
        "color:var(--muted)}"
        "input,select{width:100%;padding:11px 12px;background:var(--panel2);"
        "border:1px solid var(--border);color:var(--white);font:inherit}"
        "input:focus,select:focus{outline:1px solid var(--pink);border-color:var(--pink)}"
        ".btn{display:inline-flex;align-items:center;justify-content:center;gap:10px;"
        "min-height:46px;padding:12px 20px;border:1px solid var(--pink);"
        "background:var(--pink);color:#110b16;font-size:12px;font-weight:750;"
        "text-decoration:none;cursor:pointer;width:100%}"
        ".btn:hover{filter:brightness(1.05)}"
        ".btn:disabled{opacity:.45;cursor:not-allowed;filter:none}"
        ".btn.ghost{background:#291324;border-color:#78355f;color:var(--white)}"
        ".check{display:flex;align-items:center;gap:10px;margin:10px 0;"
        "font-size:14px;color:var(--white)}"
        ".check input{width:auto}"
        "#countdown{font-style:italic;font-weight:950;letter-spacing:-3px;"
        "font-size:clamp(64px,22vw,96px);line-height:1;color:var(--lime);"
        "min-height:1.1em;margin:8px 0;text-align:center}"
        "#status{color:var(--muted);font-size:13px;font-weight:700;"
        "letter-spacing:.04em;text-transform:uppercase;margin:0 0 18px;text-align:center}"
        ".tree{display:flex;flex-direction:column;align-items:center;gap:10px;"
        "margin:8px auto 18px;padding:16px 20px;background:var(--panel);"
        "border:1px solid var(--border);width:fit-content}"
        ".tree .lamp{width:42px;height:42px;border-radius:50%;"
        "background:#1a1824;border:2px solid var(--border);"
        "box-shadow:inset 0 0 12px rgba(0,0,0,.5);transition:background .15s,box-shadow .15s,border-color .15s}"
        ".tree .lamp.red.on{background:#e10600;border-color:#ff6b5a;"
        "box-shadow:0 0 18px #e10600}"
        ".tree .lamp.y1.on,.tree .lamp.y2.on{background:#f5c518;border-color:#ffe08a;"
        "box-shadow:0 0 18px #f5c518}"
        ".tree .lamp.green.on{background:#00c853;border-color:#7dffb0;"
        "box-shadow:0 0 22px #00c853}"
        ".flash{color:var(--blue);font-size:13px;font-weight:700;margin:0 0 12px}"
        ".hint{font-size:13px;color:var(--muted);margin:0 0 12px}"
        ".foot{margin-top:28px;font-size:12px;color:var(--muted)}"
        ".foot a{color:var(--blue)}"
    )


def _i18n_js():
    """Client i18n: RO/EN, persisted in localStorage for the whole UI."""
    # Keep keys short. RO uses ASCII letters only (no diacritics) so source stays
    # safe on all editors; meaning is still Romanian.
    return (
        "var I18N={lang:'ro',dict:{"
        "en:{"
        "'top':'START LIGHT / CONTROL',"
        "'nav.remote':'Remote','nav.settings':'Settings',"
        "'foot':'Powered by ',"
        "'ctrl.h1':'START.<br>THE<br><em>TREE.<\\/em>',"
        "'ctrl.lead':'Press START, wait the delay, then red -> yellow -> green. Same timing as Settings.',"
        "'status.ready':'Ready','btn.start':'START sequence',"
        "'status.starting':'Starting...','status.countdown':'Countdown - %s sec',"
        "'status.red':'Red','status.wait':'Hold...','status.yellow':'Yellow',"
        "'status.go':'GO!','status.done':'Done','status.error':'Error: ',"
        "'flash.saved':'Settings saved.',"
        "'set.h1':'SETTINGS.<br><em>TIMING.<\\/em>',"
        "'set.lead':'WiFi, lamp delays, and per-channel LED test. Same sequence the START button runs.',"
        "'p.wifi':'WiFi','l.ssid':'SSID','l.pass':'Password',"
        "'ph.ssid':'Network name','ph.pass':'Leave blank to keep current',"
        "'p.seq':'Lamp sequence',"
        "'l.red':'Red duration (sec)','l.rmin':'Random wait min (sec)',"
        "'l.rmax':'Random wait max (sec)','l.yint':'Yellow interval (sec)',"
        "'l.green':'Green off delay (sec)',"
        "'p.delay':'Start delay','l.mode':'Mode',"
        "'opt.rand':'Random (5-20 sec)','opt.fix':'Fixed',"
        "'l.fixed':'Fixed delay (sec)','l.dmin':'Random delay min (sec)',"
        "'l.dmax':'Random delay max (sec)',"
        "'btn.save':'Save settings',"
        "'p.pin':'Local PIN','l.pin':'Web PIN',"
        "'ph.pin':'4+ digits','pin.hint':'Asked on every new browser. Stored in startlight_config.json.',"
        "'pin.h1':'PIN.<br><em>LOCAL.<\\/em>',"
        "'pin.lead':'Enter the local control PIN to use this Start Light on the LAN.',"
        "'pin.label':'PIN','btn.pin':'Unlock','pin.bad':'Wrong PIN.',"
        "'title.pin':'Start Light - PIN',"
        "'p.led':'LED test',"
        "'led.hint':'Checked = ON (active-low SSR). A start sequence can clear lamps while boxes stay checked.',"
        "'led.0':'Red (GP2)','led.1':'Yellow 1 (GP3)',"
        "'led.2':'Yellow 2 (GP4)','led.3':'Green (GP5)',"
        "'btn.alloff':'All LEDs off','led.ok':'OK','led.err':'Error',"
        "'led.fail':'Failed: ','led.alloff':'All off',"
        "'404.h1':'404.<br><em>MISS.<\\/em>',"
        "'404.lead':'No page here. Back to remote or settings.',"
        "'404.remote':'Remote control','404.settings':'Settings',"
        "'title.remote':'Start Light - Remote','title.settings':'Start Light - Settings',"
        "'title.404':'Start Light - 404'"
        "},"
        "ro:{"
        "'top':'START LIGHT / CONTROL',"
        "'nav.remote':'Control','nav.settings':'Setari',"
        "'foot':'Powered by ',"
        "'ctrl.h1':'START.<br>LUMINI.<br><em>GO.<\\/em>',"
        "'ctrl.lead':'Apasa START, asteapta delay-ul, apoi rosu -> galben -> verde. Aceleasi timpuri ca la Setari.',"
        "'status.ready':'Pregatit','btn.start':'START secventa',"
        "'status.starting':'Pornire...','status.countdown':'Numaratoare - %s sec',"
        "'status.red':'Rosu','status.wait':'Asteptare...','status.yellow':'Galben',"
        "'status.go':'GO!','status.done':'Gata','status.error':'Eroare: ',"
        "'flash.saved':'Setari salvate.',"
        "'set.h1':'SETARI.<br><em>TIMPI.<\\/em>',"
        "'set.lead':'WiFi, timpuri la lumini si test LED pe canal. Aceeasi secventa ca butonul START.',"
        "'p.wifi':'WiFi','l.ssid':'SSID','l.pass':'Parola',"
        "'ph.ssid':'Nume retea','ph.pass':'Lasati gol ca sa pastreti parola',"
        "'p.seq':'Secventa lumini',"
        "'l.red':'Durata rosu (sec)','l.rmin':'Asteptare random min (sec)',"
        "'l.rmax':'Asteptare random max (sec)','l.yint':'Interval galben (sec)',"
        "'l.green':'Durata verde (sec)',"
        "'p.delay':'Delay la start','l.mode':'Mod',"
        "'opt.rand':'Random (5-20 sec)','opt.fix':'Fix',"
        "'l.fixed':'Delay fix (sec)','l.dmin':'Delay random min (sec)',"
        "'l.dmax':'Delay random max (sec)',"
        "'btn.save':'Salveaza setari',"
        "'p.pin':'PIN local','l.pin':'PIN web',"
        "'ph.pin':'Minim 4 cifre','pin.hint':'Cerut in browser. Se schimba in startlight_config.json sau aici.',"
        "'pin.h1':'PIN.<br><em>LOCAL.<\\/em>',"
        "'pin.lead':'Introdu PIN-ul local ca sa folosesti Start Light pe retea.',"
        "'pin.label':'PIN','btn.pin':'Deblocheaza','pin.bad':'PIN gresit.',"
        "'title.pin':'Start Light - PIN',"
        "'p.led':'Test LED',"
        "'led.hint':'Bifat = APRINS (SSR active-low). O secventa de start poate stinge luminile cat timp bifele raman.',"
        "'led.0':'Rosu (GP2)','led.1':'Galben 1 (GP3)',"
        "'led.2':'Galben 2 (GP4)','led.3':'Verde (GP5)',"
        "'btn.alloff':'Toate LED-urile off','led.ok':'OK','led.err':'Eroare',"
        "'led.fail':'Esec: ','led.alloff':'Toate off',"
        "'404.h1':'404.<br><em>LIPSA.<\\/em>',"
        "'404.lead':'Nu exista aceasta pagina. Inapoi la control sau setari.',"
        "'404.remote':'Control remote','404.settings':'Setari',"
        "'title.remote':'Start Light - Control','title.settings':'Start Light - Setari',"
        "'title.404':'Start Light - 404'"
        "}"
        "},"
        "t:function(k){var d=this.dict[this.lang]||this.dict.en;"
        "var v=d[k];if(v==null)v=(this.dict.en[k]||k);return v},"
        "tf:function(k,a){return this.t(k).replace('%s',a)},"
        "apply:function(){"
        "document.documentElement.lang=this.lang;"
        "var n=document.querySelectorAll('[data-i18n]');"
        "for(var i=0;i<n.length;i++){var el=n[i],k=el.getAttribute('data-i18n');"
        "if(el.getAttribute('data-i18n-html')!=null)el.innerHTML=this.t(k);"
        "else el.textContent=this.t(k)}"
        "var p=document.querySelectorAll('[data-i18n-placeholder]');"
        "for(var j=0;j<p.length;j++)p[j].placeholder=this.t(p[j].getAttribute('data-i18n-placeholder'));"
        "var tk=document.documentElement.getAttribute('data-i18n-title');"
        "if(tk)document.title=this.t(tk);"
        "var b=document.querySelectorAll('.lang-switch button');"
        "for(var x=0;x<b.length;x++)b[x].setAttribute('aria-pressed',"
        "b[x].getAttribute('data-lang')===this.lang?'true':'false')"
        "},"
        "set:function(lang){if(lang!=='en'&&lang!=='ro')lang='ro';this.lang=lang;"
        "try{localStorage.setItem('sl_lang',lang)}catch(e){}this.apply()},"
        "init:function(){var s=null;try{s=localStorage.getItem('sl_lang')}catch(e){}"
        "this.lang=(s==='en'||s==='ro')?s:'ro';this.apply()}"
        "};"
    )


def _shell(title_key, nav, body):
    """Page chrome matching RCDrift.ro: topline, // brand, RO/EN switch.

    Style in <head>; i18n script at end of <body> so a truncated send still
    leaves visible markup (default Romanian) instead of a blank page.
    """
    c_on = ' class="on"' if nav == "control" else ""
    s_on = ' class="on"' if nav == "settings" else ""
    return (
        "<!DOCTYPE html><html lang=\"ro\" data-i18n-title=\"" + title_key + "\"><head>"
        "<meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<meta name=\"theme-color\" content=\"#0a0910\">"
        "<title>Start Light</title>"
        "<style>" + _css() + "</style>"
        "</head><body>"
        "<div class=\"topline\">"
        "<span data-i18n=\"top\">START LIGHT / CONTROL</span>"
        "<span class=\"top-right\"><i></i>RCDRIFT.RO</span></div>"
        "<div class=\"wrap\">"
        "<a class=\"brand\" href=\"/\"><span class=\"sl\">//</span>"
        "<span>START<span class=\"hi\">LIGHT</span><small>.ro</small></span></a>"
        "<p class=\"powered\"><span data-i18n=\"foot\">Powered by </span>"
        "<a href=\"https://www.rcdrift.ro\" target=\"_blank\" rel=\"noopener\">rcdrift.ro</a></p>"
        "<div class=\"bar\">"
        "<nav aria-label=\"Pages\">"
        "<a href=\"/\"" + c_on + " data-i18n=\"nav.remote\">Control</a>"
        "<a href=\"/settings\"" + s_on + " data-i18n=\"nav.settings\">Setari</a>"
        "</nav>"
        "<div class=\"lang-switch\" role=\"group\" aria-label=\"Language\">"
        "<button type=\"button\" data-lang=\"ro\" onclick=\"I18N.set('ro')\">RO</button>"
        "<button type=\"button\" data-lang=\"en\" onclick=\"I18N.set('en')\">EN</button>"
        "</div></div>"
        + body +
        "</div>"
        "<script>" + _i18n_js() + "I18N.init()</script>"
        "</body></html>"
    )


def _is_alnum(ch):
    """MicroPython str often lacks isalnum(); use range checks instead."""
    return ("0" <= ch <= "9") or ("A" <= ch <= "Z") or ("a" <= ch <= "z")


def _valid_api_base(base):
    """Local-only check — never opens a network connection."""
    try:
        from cloud import usable_api_base
        return usable_api_base(base)
    except Exception:
        return False


def _normalize_pair_code(code):
    code = (code or "").strip().upper()
    if not code or len(code) > 16:
        return ""
    for ch in code:
        if not _is_alnum(ch):
            return ""
    return code


def _cloud_redirect(conn, msg, href="/settings"):
    """Tiny reply after cloud POSTs — avoid rebuilding the full settings page
    on the same request (Pico W RAM is tight right after a JSON write)."""
    body = (
        "<!DOCTYPE html><html><head><meta charset=utf-8>"
        "<meta name=viewport content=\"width=device-width,initial-scale=1\">"
        "<title>Start Light</title></head><body style=\"font-family:sans-serif;"
        "background:#0a0910;color:#f6f3fb;padding:24px\">"
        "<p>" + html_escape(msg) + "</p>"
        "<p><a href=\"" + href + "\" style=\"color:#48ccfa\">Inapoi la setari</a> · "
        "<a href=\"/\" style=\"color:#48ccfa\">Control</a></p>"
        "</body></html>"
    ).encode()
    _send_all(
        conn,
        (
            b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"Cache-Control: no-store\r\nConnection: close\r\n\r\n" + body
        ),
    )
    conn.close()


def _cloud_panel():
    """Optional rcdrift.ro pairing — standalone works without this."""
    try:
        from cloud import load, status_line, DEFAULT_API_BASE
        cfg = load()
        status = status_line()
        base = html_escape(cfg.get("api_base") or DEFAULT_API_BASE)
        event = html_escape(cfg.get("event_id") or "-")
    except Exception:
        status, base, event = "Local", "https://staging.rcdrift.ro", "-"
    return (
        "<div class=\"panel\" style=\"margin-top:16px\"><h2>rcdrift.ro</h2>"
        "<p class=\"hint\">Optional. Fara legare = Start Light local (standalone).</p>"
        "<p class=\"hint\">Salveaza URL doar scrie pe Pico — nu apeleaza site-ul. "
        "Imperecheaza necesita cod de pe organizer.</p>"
        "<p class=\"hint\">Status: <strong>" + html_escape(status) + "</strong> · event: "
        + event + "</p>"
        "<form method=\"POST\" action=\"/settings\">"
        "<input type=\"hidden\" name=\"cloud_action\" value=\"save_base\">"
        "<label>API base</label>"
        "<input type=\"url\" name=\"cloud_api_base\" maxlength=\"96\" value=\"" + base + "\">"
        "<button class=\"btn ghost\" type=\"submit\" style=\"margin-top:10px\">Salveaza URL</button>"
        "</form>"
        "<form method=\"POST\" action=\"/settings\" style=\"margin-top:12px\">"
        "<input type=\"hidden\" name=\"cloud_action\" value=\"pair\">"
        "<label>Cod impartire (de pe site)</label>"
        "<input type=\"text\" name=\"pair_code\" maxlength=\"16\" required "
        "autocomplete=\"off\" placeholder=\"ABC123\">"
        "<button class=\"btn\" type=\"submit\" style=\"margin-top:10px\">Imperecheaza</button>"
        "</form>"
        "<form method=\"POST\" action=\"/settings\" style=\"margin-top:12px\">"
        "<input type=\"hidden\" name=\"cloud_action\" value=\"unpair\">"
        "<button class=\"btn ghost\" type=\"submit\">Anuleaza legatura (standalone)</button>"
        "</form></div>"
    )


def serve_settings(settings):
    """Generate settings page HTML"""
    mode0 = "selected" if settings["start_delay_mode"] == 0 else ""
    mode1 = "selected" if settings["start_delay_mode"] == 1 else ""
    body = (
        "<h1 data-i18n=\"set.h1\" data-i18n-html>SETARI.<br><em>TIMPI.</em></h1>"
        "<p class=\"lead\" data-i18n=\"set.lead\">WiFi, timpuri la lumini si test LED pe canal.</p>"
        "<form method=\"POST\" action=\"/settings\">"
        "<div class=\"panel\"><h2 data-i18n=\"p.wifi\">WiFi</h2>"
        "<label data-i18n=\"l.ssid\">SSID</label>"
        "<input type=\"text\" name=\"wifi_ssid\" value=\""
        + html_escape(_get_wifi_ssid())
        + "\" data-i18n-placeholder=\"ph.ssid\" placeholder=\"Nume retea\">"
        "<label data-i18n=\"l.pass\">Parola</label>"
        "<input type=\"password\" name=\"wifi_password\" value=\""
        + html_escape(_get_wifi_password())
        + "\" data-i18n-placeholder=\"ph.pass\" placeholder=\"Lasati gol ca sa pastreti parola\">"
        "</div>"
        "<div class=\"panel\"><h2 data-i18n=\"p.seq\">Secventa lumini</h2>"
        "<label data-i18n=\"l.red\">Durata rosu (sec)</label>"
        "<input type=\"number\" name=\"red_duration\" step=\"0.1\" min=\"0.5\" max=\"5\" value=\""
        + str(settings["red_duration"]) + "\">"
        "<label data-i18n=\"l.rmin\">Asteptare random min (sec)</label>"
        "<input type=\"number\" name=\"random_wait_min\" step=\"0.1\" min=\"0\" max=\"10\" value=\""
        + str(settings["random_wait_min"]) + "\">"
        "<label data-i18n=\"l.rmax\">Asteptare random max (sec)</label>"
        "<input type=\"number\" name=\"random_wait_max\" step=\"0.1\" min=\"0\" max=\"10\" value=\""
        + str(settings["random_wait_max"]) + "\">"
        "<label data-i18n=\"l.yint\">Interval galben (sec)</label>"
        "<input type=\"number\" name=\"yellow_interval\" step=\"0.1\" min=\"0.1\" max=\"2\" value=\""
        + str(settings["yellow_interval"]) + "\">"
        "<label data-i18n=\"l.green\">Durata verde (sec)</label>"
        "<input type=\"number\" name=\"green_off_delay\" step=\"0.1\" min=\"1\" max=\"10\" value=\""
        + str(settings["green_off_delay"]) + "\">"
        "</div>"
        "<div class=\"panel\"><h2 data-i18n=\"p.delay\">Delay la start</h2>"
        "<label data-i18n=\"l.mode\">Mod</label>"
        "<select name=\"start_delay_mode\">"
        "<option value=\"0\" " + mode0 + " data-i18n=\"opt.rand\">Random (5-20 sec)</option>"
        "<option value=\"1\" " + mode1 + " data-i18n=\"opt.fix\">Fix</option>"
        "</select>"
        "<label data-i18n=\"l.fixed\">Delay fix (sec)</label>"
        "<input type=\"number\" name=\"start_delay_fixed\" min=\"1\" max=\"60\" value=\""
        + str(settings["start_delay_fixed"]) + "\">"
        "<label data-i18n=\"l.dmin\">Delay random min (sec)</label>"
        "<input type=\"number\" name=\"start_delay_random_min\" min=\"1\" max=\"60\" value=\""
        + str(settings["start_delay_random_min"]) + "\">"
        "<label data-i18n=\"l.dmax\">Delay random max (sec)</label>"
        "<input type=\"number\" name=\"start_delay_random_max\" min=\"1\" max=\"60\" value=\""
        + str(settings["start_delay_random_max"]) + "\">"
        "</div>"
        "<div class=\"panel\"><h2 data-i18n=\"p.pin\">PIN local</h2>"
        "<p class=\"hint\" data-i18n=\"pin.hint\">Cerut in browser. Se schimba in startlight_config.json sau aici.</p>"
        "<label data-i18n=\"l.pin\">PIN web</label>"
        "<input type=\"text\" name=\"web_pin\" inputmode=\"numeric\" maxlength=\"16\" "
        "value=\"" + html_escape(str(settings.get("web_pin") or "9009")) + "\" "
        "data-i18n-placeholder=\"ph.pin\" placeholder=\"Minim 4 cifre\">"
        "</div>"
        "<button class=\"btn\" type=\"submit\" data-i18n=\"btn.save\">Salveaza setari</button>"
        "</form>"
        + _cloud_panel()
        + "<div class=\"panel\" style=\"margin-top:16px\"><h2 data-i18n=\"p.led\">Test LED</h2>"
        "<p class=\"hint\" data-i18n=\"led.hint\">Bifat = APRINS.</p>"
        "<label class=\"check\"><input type=\"checkbox\" id=\"ledTest0\" "
        "onchange=\"ledTest(0,this.checked)\"> <span data-i18n=\"led.0\">Rosu (GP2)</span></label>"
        "<label class=\"check\"><input type=\"checkbox\" id=\"ledTest1\" "
        "onchange=\"ledTest(1,this.checked)\"> <span data-i18n=\"led.1\">Galben 1 (GP3)</span></label>"
        "<label class=\"check\"><input type=\"checkbox\" id=\"ledTest2\" "
        "onchange=\"ledTest(2,this.checked)\"> <span data-i18n=\"led.2\">Galben 2 (GP4)</span></label>"
        "<label class=\"check\"><input type=\"checkbox\" id=\"ledTest3\" "
        "onchange=\"ledTest(3,this.checked)\"> <span data-i18n=\"led.3\">Verde (GP5)</span></label>"
        "<button type=\"button\" class=\"btn ghost\" style=\"margin-top:12px\" "
        "onclick=\"ledTestAllOff()\" data-i18n=\"btn.alloff\">Toate LED-urile off</button>"
        "<p id=\"ledTestMsg\" class=\"hint\"></p></div>"
        "<script>"
        "async function ledTest(n,on){var m=document.getElementById('ledTestMsg');"
        "m.textContent='...';try{var r=await fetch('/api/led?n='+n+'&on='+(on?1:0));"
        "var j=await r.json();m.textContent=j.ok?I18N.t('led.ok'):I18N.t('led.err');"
        "setTimeout(function(){m.textContent='';},1500)}"
        "catch(e){m.textContent=I18N.t('led.fail')+e}}"
        "async function ledTestAllOff(){for(var i=0;i<4;i++){"
        "document.getElementById('ledTest'+i).checked=false;"
        "await fetch('/api/led?n='+i+'&on=0')}var m=document.getElementById('ledTestMsg');"
        "m.textContent=I18N.t('led.alloff');setTimeout(function(){m.textContent='';},1500)}"
        "</script>"
    )
    return _shell("title.settings", "settings", body)


def serve_pin(bad=False):
    """Local LAN unlock — PIN from startlight_config.json (default 9009)."""
    flash = (
        "<p class=\"flash\" style=\"color:#f34ebc\" data-i18n=\"pin.bad\">PIN gresit.</p>"
        if bad else ""
    )
    body = (
        "<h1 data-i18n=\"pin.h1\" data-i18n-html>PIN.<br><em>LOCAL.</em></h1>"
        "<p class=\"lead\" data-i18n=\"pin.lead\">Introdu PIN-ul local ca sa folosesti "
        "Start Light pe retea.</p>"
        + flash
        + "<form method=\"POST\" action=\"/pin\" class=\"panel\">"
        "<label data-i18n=\"pin.label\">PIN</label>"
        "<input type=\"password\" name=\"pin\" inputmode=\"numeric\" maxlength=\"16\" "
        "autocomplete=\"one-time-code\" required autofocus>"
        "<button class=\"btn\" type=\"submit\" style=\"margin-top:14px\" "
        "data-i18n=\"btn.pin\">Deblocheaza</button>"
        "</form>"
    )
    return _shell("title.pin", "control", body)


def serve_control(show_saved=False):
    """Generate remote control page HTML"""
    try:
        from cloud import is_paired
        paired = bool(is_paired())
    except Exception:
        paired = False
    flash = (
        "<p class=\"flash\" id=\"savedMsg\" data-i18n=\"flash.saved\">Setari salvate.</p>"
        "<script>setTimeout(function(){var m=document.getElementById('savedMsg');"
        "if(m)m.style.display='none'},4000)</script>"
    ) if show_saved else ""
    body = (
        "<h1 id=\"heroLine\" data-i18n=\"ctrl.h1\" data-i18n-html>"
        "START.<br>LUMINI.<br><em>GO.</em></h1>"
        "<p class=\"lead\" data-i18n=\"ctrl.lead\">Apasa START, asteapta delay-ul, "
        "apoi rosu -&gt; galben -&gt; verde.</p>"
        + flash
        + "<div class=\"tree\" id=\"tree\" aria-hidden=\"true\">"
        "<div class=\"lamp red\" id=\"lamp0\"></div>"
        "<div class=\"lamp y1\" id=\"lamp1\"></div>"
        "<div class=\"lamp y2\" id=\"lamp2\"></div>"
        "<div class=\"lamp green\" id=\"lamp3\"></div>"
        "</div>"
        "<div id=\"countdown\" aria-live=\"polite\"></div>"
        "<div id=\"status\" data-i18n=\"status.ready\">Pregatit</div>"
        "<button class=\"btn\" id=\"startBtn\" type=\"button\" onclick=\"startRace()\" "
        "data-i18n=\"btn.start\">START secventa</button>"
        "<script>"
        # Compact funny drift headlines (3 lines). <\/em> keeps </script> parsers happy.
        "var HERO={"
        "en:["
        "'SLIDE.<br>DON\\'T<br><em>GRIP.<\\/em>',"
        "'SMOKE.<br>THE<br><em>TIRES.<\\/em>',"
        "'MORE<br>STEERING<br><em>INPUT.<\\/em>',"
        "'HOLD<br>THAT<br><em>ANGLE.<\\/em>',"
        "'CLUTCH<br>KICK<br><em>GO.<\\/em>',"
        "'ENTRY.<br>THEN<br><em>CHAOS.<\\/em>',"
        "'TIRES<br>SAY<br><em>BYE.<\\/em>',"
        "'SIDEWAYS<br>IS<br><em>FORWARD.<\\/em>',"
        "'HANDBRAKE<br>IS<br><em>LOVE.<\\/em>',"
        "'IF IN<br>DOUBT<br><em>THROTTLE.<\\/em>',"
        "'DRIFT NOW<br>CRY<br><em>LATER.<\\/em>',"
        "'FULL<br>SEND<br><em>MODE.<\\/em>'"
        "],"
        "ro:["
        "'ALUNECA.<br>NU<br><em>TRAGE.<\\/em>',"
        "'FUM.<br>DIN<br><em>CAUCIUC.<\\/em>',"
        "'UNGHI.<br>MAI<br><em>MULT.<\\/em>',"
        "'DERAPA.<br>CU<br><em>ZAMBET.<\\/em>',"
        "'FRIANA<br>DE<br><em>MANA.<\\/em>',"
        "'INTRARE.<br>APOI<br><em>HAOS.<\\/em>',"
        "'CAUCIUCUL<br>ZICE<br><em>PA.<\\/em>',"
        "'DE-A<br>LATUL<br><em>E DRUM.<\\/em>',"
        "'DACA<br>INDOIALA<br><em>GAZ.<\\/em>',"
        "'FULL<br>SEND<br><em>ACUM.<\\/em>',"
        "'START.<br>LUMINI.<br><em>GO.<\\/em>',"
        "'SENSEI<br>ZICE<br><em>MAI TARI.<\\/em>'"
        "]"
        "};"
        "function sleep(s){return new Promise(function(r){setTimeout(r,Math.round(s*1000))})}"
        "function setLamps(on){for(var i=0;i<4;i++){"
        "var el=document.getElementById('lamp'+i);"
        "if(el){if(on[i])el.classList.add('on');else el.classList.remove('on')}}}"
        "function spinHero(){"
        "var list=HERO[I18N.lang]||HERO.en;"
        "var h=document.getElementById('heroLine');"
        "if(!h||!list||!list.length)return;"
        "h.removeAttribute('data-i18n');"
        "h.removeAttribute('data-i18n-html');"
        "h.innerHTML=list[Math.floor(Math.random()*list.length)]}"
        "var PAIRED=" + ("true" if paired else "false") + ";"
        "async function syncRaceButton(){if(!PAIRED)return;"
        "try{var r=await fetch('/api/cloud/status');var j=await r.json();"
        "if(j.paired){var b=document.getElementById('startBtn');b.textContent=(I18N.lang==='en'?j.labelEn:j.label)||'RCDrift';b.disabled=!j.canPress;"
        "document.getElementById('status').textContent=(I18N.lang==='en'?j.blockedEn:j.blocked)||'RCDrift';}}catch(e){}}"
        "if(PAIRED){setInterval(syncRaceButton,1500);syncRaceButton();}"
        "async function startRace(){"
        "var btn=document.getElementById('startBtn');"
        "var cd=document.getElementById('countdown');"
        "var st=document.getElementById('status');"
        "btn.disabled=true;st.removeAttribute('data-i18n');"
        "spinHero();"
        "setLamps([0,0,0,0]);cd.textContent='';"
        "st.textContent=I18N.t('status.starting');"
        "try{var r=await fetch('/start');var j=await r.json();"
        "if(j.managed){st.textContent=j.error||j.label||(j.ok?\"RCDrift: OK\":\"RCDrift: așteaptă\");return;}"
        "if(j.ok){"
        "var d=j.delay|0;"
        "for(var i=d;i>=1;i--){cd.textContent=i;"
        "st.textContent=I18N.tf('status.countdown',i);await sleep(1)}"
        "cd.textContent='';"
        "setLamps([1,0,0,0]);st.textContent=I18N.t('status.red');"
        "await sleep(j.red_duration);"
        "st.textContent=I18N.t('status.wait');await sleep(j.random_wait);"
        "setLamps([1,1,0,0]);st.textContent=I18N.t('status.yellow');"
        "await sleep(j.yellow_interval);"
        "setLamps([1,1,1,0]);st.textContent=I18N.t('status.yellow');"
        "await sleep(j.yellow_interval);"
        "setLamps([1,1,1,1]);cd.textContent='GO!';"
        "st.textContent=I18N.t('status.go');"
        "await sleep(j.green_off_delay);"
        "setLamps([0,0,0,0]);cd.textContent='';"
        "st.textContent=I18N.t('status.done');await sleep(0.6)"
        "}}catch(e){st.textContent=I18N.t('status.error')+e}"
        "finally{setLamps([0,0,0,0]);cd.textContent='';"
        "st.setAttribute('data-i18n','status.ready');"
        "st.textContent=I18N.t('status.ready');btn.disabled=false}}"
        "</script>"
    )
    return _shell("title.remote", "control", body)



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
        cookies = _parse_cookies(data)
        print("[Web] %s %s" % (method, path))
        response = ""
        content_type = "text/html"

        # Local PIN gate (LAN). /pin is the only unlocked HTML entry.
        if path == "/pin":
            if method == "POST" and body:
                form = parse_form(body)
                pin = str((form or {}).get("pin") or "").strip()
                if pin and pin == _expected_pin(settings):
                    print("[Web] PIN ok")
                    extra_headers = (
                        b"Set-Cookie: sl_pin="
                        + pin.encode()
                        + b"; Path=/; Max-Age=604800; SameSite=Lax\r\n"
                    )
                    _send_all(
                        conn,
                        b"HTTP/1.1 303 See Other\r\nLocation: /\r\n"
                        + extra_headers
                        + b"Connection: close\r\n\r\n",
                    )
                    conn.close()
                    return
                print("[Web] PIN rejected")
                response = serve_pin(bad=True)
            else:
                response = serve_pin(bad=False)
            if isinstance(response, str):
                body_bytes = response.encode("utf-8")
            else:
                body_bytes = response
            _send_all(
                conn,
                b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                b"Content-Length: " + str(len(body_bytes)).encode() + b"\r\n"
                b"Cache-Control: no-store\r\nConnection: close\r\n\r\n",
            )
            _send_all(conn, body_bytes)
            conn.close()
            return

        if not _pin_unlocked(settings, cookies):
            if path.startswith("/api") or path == "/start":
                msg = json.dumps({"ok": False, "error": "PIN required", "auth": False})
                raw = msg.encode()
                _send_all(
                    conn,
                    b"HTTP/1.1 401 Unauthorized\r\nContent-Type: application/json\r\n"
                    b"Content-Length: " + str(len(raw)).encode() + b"\r\n"
                    b"Connection: close\r\n\r\n" + raw,
                )
                conn.close()
                return
            _send_all(
                conn,
                b"HTTP/1.1 303 See Other\r\nLocation: /pin\r\n"
                b"Cache-Control: no-store\r\nConnection: close\r\n\r\n",
            )
            conn.close()
            return

        if path == "/" or path == "/control":
            response = serve_control(show_saved=(query.get("saved") == "1"))
        elif path == "/settings":
            if method == "POST" and body:
                form = parse_form(body)
                if form:
                    try:
                        cloud_action = (form.get("cloud_action") or "").strip()
                        if cloud_action:
                            try:
                                import gc
                                gc.collect()
                            except Exception:
                                pass
                            from cloud import load as cloud_load, save as cloud_save, pair, unpair, DEFAULT_API_BASE
                            if cloud_action == "save_base":
                                base = (form.get("cloud_api_base") or DEFAULT_API_BASE).strip().rstrip("/")
                                print("[Web] Cloud save_base", base)
                                if not _valid_api_base(base):
                                    print("[Web] Rejected API base")
                                    _cloud_redirect(conn, "URL invalid. Foloseste https://host fara spatiu.")
                                else:
                                    cfg = cloud_load()
                                    cfg["api_base"] = base
                                    cloud_save(cfg)
                                    print("[Web] Cloud API base saved")
                                    _cloud_redirect(conn, "URL salvat pe Pico (fara apel retea).")
                                return
                            if cloud_action == "pair":
                                code = _normalize_pair_code(form.get("pair_code"))
                                if not code:
                                    print("[Web] Pair skipped: empty/invalid code")
                                    _cloud_redirect(conn, "Cod lipsa. Standalone ramane activ.")
                                    return
                                _cloud_redirect(conn, "Se incearca imperecherea… Reincarca setarile in cateva secunde.")
                                print("[Web] Pairing with code…")
                                try:
                                    ok, err = pair(code)
                                    print("[Web] Pair result:", ok, err)
                                except Exception as e:
                                    print("[Web] Pair error:", type(e).__name__, e)
                                return
                            if cloud_action == "unpair":
                                print("[Web] Cloud unpair")
                                unpair()
                                _cloud_redirect(conn, "Dezlegat — standalone.")
                                return
                            _cloud_redirect(conn, "Actiune necunoscuta.")
                            return
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
                        new_pin = str(form.get("web_pin") or "").strip()
                        if new_pin and len(new_pin) <= 16:
                            settings["web_pin"] = new_pin
                        from settings import save
                        save(settings)
                        print("[Web] Settings saved, redirecting to /")
                        # Refresh cookie if PIN changed so this browser stays unlocked
                        pin_cookie = (
                            b"Set-Cookie: sl_pin="
                            + _expected_pin(settings).encode()
                            + b"; Path=/; Max-Age=604800; SameSite=Lax\r\n"
                        )
                        _send_all(
                            conn,
                            b"HTTP/1.1 303 See Other\r\nLocation: /?saved=1\r\n"
                            + pin_cookie
                            + b"Connection: close\r\n\r\n",
                        )
                        conn.close()
                        return
                    except Exception as e:
                        print("[Web] Settings save error:", e)
            response = serve_settings(settings)
        elif path == "/api/cloud/status":
            from cloud import status_snapshot
            content_type = "application/json"
            response = json.dumps(status_snapshot())
        elif path == "/start":
            from cloud import is_paired, local_press
            if is_paired():
                reply = local_press()
                reply["managed"] = True
                response = json.dumps(reply)
                _send_all(conn, ("HTTP/1.0 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(response.encode())).encode() + response.encode())
                return
            global start_delay_value, start_plan
            import random
            from settings import get_start_delay
            delay = int(get_start_delay(settings))
            rand_wait = random.uniform(
                settings["random_wait_min"], settings["random_wait_max"]
            )
            # Same numbers for Pico lamps and browser tree viz
            start_plan = {
                "ok": True,
                "delay": delay,
                "red_duration": float(settings["red_duration"]),
                "random_wait": float(rand_wait),
                "yellow_interval": float(settings["yellow_interval"]),
                "green_off_delay": float(settings["green_off_delay"]),
            }
            start_requested = True
            start_delay_value = delay
            print(
                "[Web] Start plan delay=%ds red=%.2f wait=%.2f y=%.2f g=%.2f"
                % (
                    delay,
                    start_plan["red_duration"],
                    start_plan["random_wait"],
                    start_plan["yellow_interval"],
                    start_plan["green_off_delay"],
                )
            )
            content_type = "application/json"
            response = json.dumps(start_plan)
        elif path == "/api/settings":
            content_type = "application/json"
            public = dict(settings)
            public.pop("web_pin", None)
            response = json.dumps(public)
        elif path == "/api/led":
            from cloud import is_paired
            if is_paired():
                response = json.dumps({"ok": False, "error": "RCDrift controls the lamps. Unpair for a local lamp test."})
                _send_all(conn, ("HTTP/1.0 409 Conflict\r\nContent-Type: application/json\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(response.encode())).encode() + response.encode())
                return
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
            response = _shell(
                "title.404",
                "control",
                "<h1 data-i18n=\"404.h1\" data-i18n-html>404.<br><em>LIPSA.</em></h1>"
                "<p class=\"lead\" data-i18n=\"404.lead\">Nu exista aceasta pagina.</p>"
                "<a class=\"btn\" href=\"/\" data-i18n=\"404.remote\">Control remote</a>"
                "<p style=\"height:10px\"></p>"
                "<a class=\"btn ghost\" href=\"/settings\" data-i18n=\"404.settings\">Setari</a>",
            )

        if content_type == "text/html":
            content_type = "text/html; charset=utf-8"
        elif content_type == "application/json":
            content_type = "application/json; charset=utf-8"
        if isinstance(response, str):
            body = response.encode("utf-8")
        else:
            body = response
        cache = b""
        if content_type.startswith("text/html"):
            cache = b"Cache-Control: no-store\r\n"
        headers = (
            b"HTTP/1.1 200 OK\r\nContent-Type: "
            + content_type.encode()
            + b"\r\nContent-Length: "
            + str(len(body)).encode()
            + b"\r\n"
            + cache
            + b"Connection: close\r\n\r\n"
        )
        _send_all(conn, headers)
        _send_all(conn, body)
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


def get_start_plan():
    """Timing plan from last /start (shared with lamp sequence)."""
    global start_plan
    return start_plan


def clear_start_requested():
    global start_requested
    start_requested = False
