from datetime import datetime
import asyncio
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import threading
import time

import tornado.httpserver
import tornado.ioloop
import tornado.web
import tornado.websocket

# Windows consoles default to cp1252 and choke on emoji in log lines.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get('TMS_PORT', 5050))
BIND_HOST = os.environ.get('TMS_HOST', '0.0.0.0')
CONFIG_FILE_PATH = os.path.join(BASE_DIR, 'config.json')
USERS_FILE = os.path.join(BASE_DIR, 'users.json')
FRONTEND_DIR = os.path.normpath(os.path.join(BASE_DIR, '../frontend'))
SAVED_SPLS_FILE = os.path.join(BASE_DIR, 'saved_spls.json')
AUTOMATION_RULES_FILE = os.path.join(BASE_DIR, 'automation_rules.json')
LOG_DIR = os.path.join(BASE_DIR, 'logs')
AUDIT_LOG_FILE = os.path.join(LOG_DIR, 'audit.log')

DEFAULT_SERVER_PASS = os.environ.get('TMS_DEFAULT_SERVER_PASS', '')
SESSION_TTL = int(os.environ.get('TMS_SESSION_TTL', 8 * 3600))   # idle timeout (seconds)
DEFAULT_POLL_INTERVAL = 10                                        # seconds (config: "poll_interval")
SCREEN_POLL_TIMEOUT = 25                                          # max seconds for one screen poll
CORS_ORIGIN = os.environ.get('TMS_CORS_ORIGIN', '')               # empty = same-origin only
LOGIN_MAX_FAILS = 5
LOGIN_LOCK_SECONDS = 300

DEFAULT_CONFIG = {"screens": [], "port": 161, "community": "public"}
PRIVILEGES = {'Operator': 1, 'Manager': 2, 'Admin': 3}
CONTROL_COMMANDS = {'Play', 'Pause', 'Stop', 'Eject', 'SkipForward', 'SkipBackward', 'load_spl'}
# Automation action -> ims_soap_client.send_command() verb
AUTOMATION_ACTIONS = {
    'POWER_ON': 'power_on', 'POWER_OFF': 'power_off',
    'PLAY': 'Play', 'PAUSE': 'Pause', 'STOP': 'Stop',
}
HOST_RE = re.compile(r'^[A-Za-z0-9.\-]{0,253}$')
USERNAME_RE = re.compile(r'^[A-Za-z0-9_.\-]{3,32}$')
TIME_RE = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
DAYS = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}

# --- SNMP IMPORTS ---
PYSNMP_AVAILABLE = False
try:
    from pysnmp.hlapi.v3arch.asyncio import (get_cmd, SnmpEngine, CommunityData, UdpTransportTarget,
                                             ContextData, ObjectType, ObjectIdentity)
    PYSNMP_AVAILABLE = True
except ImportError:
    try:
        from pysnmp.hlapi.asyncio import (get_cmd, SnmpEngine, CommunityData, UdpTransportTarget,
                                          ContextData, ObjectType, ObjectIdentity)
        PYSNMP_AVAILABLE = True
    except ImportError:
        print("WARNING: pysnmp not available - projector SNMP checks disabled.")

# --- GLOBAL STATE ---
THEATERS_DATA = {}        # screen id (str) -> status dict
GLOBAL_LIBRARY = []       # aggregated CPLs
LIBRARY_LOCK = asyncio.Lock()
SESSION_TOKENS = {}       # token -> session dict
WS_CLIENTS = set()
LAST_LIBRARY_UPDATE = [0]
LOGIN_FAILS = {}          # ip -> [count, first_fail_ts, locked_until_ts]
_FILE_LOCK = threading.RLock()

os.makedirs(LOG_DIR, exist_ok=True)

# --- ENGINES ---
import ims_soap_client  # noqa: E402

sys.path.append(os.path.join(BASE_DIR, '../server_status_methods'))
import gdc_sr1000_client  # noqa: E402


# --- FILE HELPERS (atomic, locked) ---
def read_json(path, default=None):
    with _FILE_LOCK:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except Exception as e:
            print(f"WARNING: cannot read {os.path.basename(path)}: {e}")
            return default


def write_json(path, data):
    with _FILE_LOCK:
        try:
            tmp = path + ".tmp"
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            if os.path.getsize(tmp) > 0:
                os.replace(tmp, path)
                return True
        except Exception as e:
            print(f"ERROR: cannot write {os.path.basename(path)}: {e}")
        return False


def load_config():
    """Returns config dict, or None on a transient read error (callers must not treat that as empty)."""
    if not os.path.exists(CONFIG_FILE_PATH):
        return DEFAULT_CONFIG.copy()
    with _FILE_LOCK:
        try:
            with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception as e:
            print(f"WARNING: config read failed: {e}")
            return None


def save_config(cfg):
    return write_json(CONFIG_FILE_PATH, cfg)


def find_screen(cfg, screen_id):
    if not cfg or screen_id is None:
        return None
    return next((s for s in cfg.get('screens', []) if str(s.get('id')) == str(screen_id)), None)


def find_screen_by_host(cfg, host):
    if not cfg or not host:
        return None
    return next((s for s in cfg.get('screens', []) if host in (s.get('ims_ip'), s.get('projector_ip'))), None)


def screen_host(screen):
    return screen.get('ims_ip') or screen.get('projector_ip')


def is_gdc(screen):
    return screen.get('server_type') == 'GDC'


def server_creds(screen):
    return screen.get('server_user', 'Maintenance'), screen.get('server_pass') or DEFAULT_SERVER_PASS


# --- AUDIT ---
def audit_log(username, action, details=""):
    clean = lambda v: str(v).replace('\r', ' ').replace('\n', ' ')   # no log-line forging
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] User: {clean(username)} | Action: {clean(action)} | Details: {clean(details)}\n"
    try:
        with _FILE_LOCK, open(AUDIT_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(entry)
    except Exception:
        pass
    print(f"AUDIT: {entry.strip()}")


# --- PASSWORDS ---
def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    """Supports scrypt hashes and legacy plaintext (upgraded to a hash on next successful login)."""
    if not isinstance(stored, str):
        return False
    if stored.startswith("scrypt$"):
        try:
            _, salt_hex, hash_hex = stored.split("$")
            digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2 ** 14, r=8, p=1)
            return hmac.compare_digest(digest.hex(), hash_hex)
        except Exception:
            return False
    return hmac.compare_digest(password.encode(), stored.encode())


def ensure_users():
    """Create a first admin with a random password if no users exist (otherwise nobody could log in)."""
    users = read_json(USERS_FILE, None)
    if users:
        return
    pw = secrets.token_urlsafe(9)
    write_json(USERS_FILE, [{"id": "USR-001", "username": "admin", "email": "", "password": hash_password(pw),
                             "privilege": "Admin"}])
    print("=" * 60)
    print(f"FIRST RUN: created user 'admin' with password: {pw}")
    print("Change it after logging in. This is shown only once.")
    print("=" * 60)


def revoke_sessions(user_id):
    for t in [t for t, s in SESSION_TOKENS.items() if s['id'] == user_id]:
        SESSION_TOKENS.pop(t, None)


def get_session(token):
    s = SESSION_TOKENS.get(token) if token else None
    if not s:
        return None
    now = time.time()
    if now - s['last_seen'] > SESSION_TTL:
        SESSION_TOKENS.pop(token, None)
        return None
    s['last_seen'] = now
    return s


# --- POLLING ---
async def poll_screen(snmp_engine, screen, cfg):
    s_id = str(screen['id'])
    p_ip = screen.get('projector_ip', '')
    ims_ip = screen.get('ims_ip') or p_ip

    data = THEATERS_DATA.get(s_id, {
        "status": "Offline", "lamp": "OFF", "playback": "Stopped",
        "content": "No Data", "progress": 0, "remaining": "--:--",
        "temp": "0°C", "storage": "0%", "errors": []
    })
    # Merge config fields so the frontend keeps them - but never leak device credentials.
    for k, v in screen.items():
        if k in ('server_pass', 'server_user'):
            continue
        data[k] = v
    data.setdefault('ip', p_ip)

    # 1. Projector health via SNMP
    data["status"] = "Offline"
    if PYSNMP_AVAILABLE and snmp_engine and p_ip and p_ip != "0.0.0.0":
        try:
            transport = await UdpTransportTarget.create((p_ip, 161), timeout=0.3, retries=0)
            ei, es, _, _ = await get_cmd(snmp_engine, CommunityData(cfg.get('community', 'public')), transport,
                                         ContextData(), ObjectType(ObjectIdentity('1.3.6.1.2.1.1.1.0')))
            if not ei and not es:
                data["status"] = "Online"
        except Exception:
            pass

    # 2. IMS health via SOAP/REST (independent of projector)
    if ims_ip and ims_ip != "0.0.0.0":
        try:
            if is_gdc(screen):
                user, pwd = server_creds(screen)
                port = screen.get('server_port')
                host_str = f"{ims_ip}:{port}" if port else ims_ip
                ims_status = await asyncio.to_thread(gdc_sr1000_client.get_sr1000_status, host_str, user, pwd)
            else:
                ims_status = await asyncio.to_thread(ims_soap_client.get_status_data, ims_ip)

            # Surface why the server is unreachable (auth failure vs timeout vs HTTP error) for diagnosis
            data["ims_error"] = None if (ims_status and ims_status.get("connected")) else \
                (ims_status or {}).get("error", "No response")
            if ims_status and ims_status.get("connected"):
                data["status"] = "Online"
                data["playback"] = ims_status.get("playbackStatus", "Stopped")
                data["spl"] = ims_status.get("spl", "-")
                data["splId"] = ims_status.get("splId")
                data["content"] = ims_status.get("content", "No Content Loaded")
                data["cplId"] = ims_status.get("cplId")
                data["elementIndex"] = ims_status.get("elementIndex", 0)
                data["progress"] = ims_status.get("positionSec", 0)
                dur = ims_status.get("durationSec", 1)
                data["progress_pct"] = int((data["progress"] / dur) * 100) if dur and dur > 0 else 0
                data["remaining"] = ims_status.get("duration", "--:--")
                data["lamp"] = "ON" if data["playback"] == "Playing" else "OFF"
                data["storage"] = ims_status.get("storage", "0%")
                data["splPositionSec"] = ims_status.get("splPositionSec", 0)

                if is_gdc(screen):
                    data["schedules"] = []
                elif time.time() - data.get("_last_sched_fetch", 0) > 300:   # schedules: every 5 min
                    try:
                        data["schedules"] = await asyncio.to_thread(ims_soap_client.get_schedule_list, ims_ip)
                        data["_last_sched_fetch"] = time.time()
                    except Exception:
                        data["schedules"] = data.get("schedules", [])
            else:
                data["playback"] = "Offline" if data["status"] == "Offline" else "Stopped"
                data["content"] = "No Data" if data["status"] == "Offline" else "No Content"
        except Exception as e:
            print(f"POLL: IMS error for {screen.get('name')}: {e}")
            data["playback"] = "Offline"
            data["schedules"] = []
    else:
        data["playback"] = "Offline"
        data["content"] = "No Data"
        data["schedules"] = []

    # Don't resurrect a screen deleted while we were polling
    current = load_config()
    if current is not None and find_screen(current, s_id):
        THEATERS_DATA[s_id] = data


# --- AUTOMATION ENGINE ---
class AutomationEngine:
    def __init__(self):
        self.rules = []
        self._fired = {}   # rule id -> "YYYYmmddHHMM" of last trigger (kept out of the rules file)
        self.load_rules()

    def load_rules(self):
        rules = read_json(AUTOMATION_RULES_FILE, None)
        if isinstance(rules, list):
            self.rules = rules
        else:
            self.rules = [{
                "id": "rule-001", "name": "Evening Shutdown", "type": "schedule", "time": "23:00",
                "days": sorted(DAYS), "action": "POWER_OFF", "targets": "all", "enabled": False
            }]
            self.save_rules()

    def save_rules(self):
        write_json(AUTOMATION_RULES_FILE, [{k: v for k, v in r.items() if not k.startswith('_')} for r in self.rules])

    async def evaluate_rules(self):
        now = datetime.now()
        current_time, current_day, stamp = now.strftime("%H:%M"), now.strftime("%a"), now.strftime("%Y%m%d%H%M")
        for rule in list(self.rules):
            if not rule.get('enabled') or rule.get('type') != 'schedule':
                continue
            if rule.get('time') != current_time or current_day not in rule.get('days', []):
                continue
            if self._fired.get(rule['id']) == stamp:
                continue
            self._fired[rule['id']] = stamp
            print(f"AUTO: Triggering rule '{rule.get('name')}' ({rule.get('action')})")
            await self.execute_action(rule['action'], rule.get('targets'))

    async def execute_action(self, action, targets):
        cfg = load_config()
        verb = AUTOMATION_ACTIONS.get(action)
        if not cfg or not verb:
            audit_log("SYSTEM_AUTO", f"AUTO_{action}", "skipped: no config or unknown action")
            return
        screens = cfg.get('screens', [])
        if targets != 'all':
            ids = {str(t) for t in (targets if isinstance(targets, list) else [targets])}
            screens = [s for s in screens if str(s['id']) in ids]

        for screen in screens:
            host = screen_host(screen)
            if is_gdc(screen) or not host:
                audit_log("SYSTEM_AUTO", f"AUTO_{action}_SKIPPED", f"{screen.get('name')}: unsupported/no host")
                continue
            try:
                res = await asyncio.to_thread(ims_soap_client.send_command, host, verb)
                ok = isinstance(res, dict) and res.get('status') == 'ok'
                detail = f"Target: {screen.get('name')} ({host})" + ("" if ok else f" FAILED: {res}")
                audit_log("SYSTEM_AUTO", f"AUTO_{action}" + ("" if ok else "_FAILED"), detail)
            except Exception as e:
                audit_log("SYSTEM_AUTO", f"AUTO_{action}_FAILED", f"{screen.get('name')}: {e}")


GLOBAL_AUTO_ENGINE = AutomationEngine()


def validate_rule(rule):
    if not isinstance(rule, dict):
        return "Invalid rule"
    if not str(rule.get('name', '')).strip():
        return "Rule name required"
    if rule.get('type', 'schedule') != 'schedule':
        return "Unsupported rule type"
    if not TIME_RE.match(str(rule.get('time', ''))):
        return "Time must be HH:MM"
    days = rule.get('days')
    if not isinstance(days, list) or not days or not set(days) <= DAYS:
        return "Invalid days"
    if rule.get('action') not in AUTOMATION_ACTIONS:
        return f"Action must be one of {sorted(AUTOMATION_ACTIONS)}"
    t = rule.get('targets', 'all')
    if t != 'all' and not isinstance(t, (list, str)):
        return "Invalid targets"
    return None


async def update_global_library():
    global GLOBAL_LIBRARY
    async with LIBRARY_LOCK:
        cfg = load_config()
        if not cfg:
            return
        new_library = {}

        def fetch_all():
            for screen in cfg.get('screens', []):
                if is_gdc(screen):
                    continue   # Dolby SOAP only
                ims_ip = screen_host(screen)
                if not ims_ip:
                    continue
                try:
                    cpls = ims_soap_client.get_cpl_list(ims_ip)
                    kdms = ims_soap_client.get_kdm_list(ims_ip)
                    for c in cpls:
                        uuid = c['uuid']
                        kdm_stat = "Free" if not c.get('encrypted', True) else kdms.get(uuid, "Missing")
                        if uuid not in new_library:
                            new_library[uuid] = {**c, "screens": [screen['name']], "kdm": kdm_stat}
                        elif screen['name'] not in new_library[uuid]["screens"]:
                            new_library[uuid]["screens"].append(screen['name'])
                except Exception as e:
                    print(f"LIBRARY: {screen.get('name')} failed: {e}")

        try:
            print("LIBRARY: Syncing global library from screens...")
            await asyncio.to_thread(fetch_all)
            GLOBAL_LIBRARY = list(new_library.values())
            print(f"LIBRARY: sync complete, {len(GLOBAL_LIBRARY)} items.")
        except Exception as e:
            print(f"LIBRARY: sync failed: {e}")


# --- BROADCAST ---
async def broadcast_status():
    msg = json.dumps({"type": "status", "data": THEATERS_DATA})
    for client in list(WS_CLIENTS):
        if not get_session(client.token):
            WS_CLIENTS.discard(client)
            client.close(4401, "Session expired")
            continue
        try:
            await client.write_message(msg)
        except Exception:
            WS_CLIENTS.discard(client)


async def tms_polling_loop():
    """Poll every screen, prune deleted ones, push status to WebSocket clients, sync library."""
    await asyncio.sleep(2)
    snmp_engine = SnmpEngine() if PYSNMP_AVAILABLE else None
    while True:
        interval = DEFAULT_POLL_INTERVAL
        try:
            cfg = load_config()
            if cfg is None:
                await asyncio.sleep(1)
                continue
            try:
                interval = max(2, float(cfg.get('poll_interval', DEFAULT_POLL_INTERVAL)))
            except (TypeError, ValueError):
                pass

            screens = cfg.get('screens', [])
            results = await asyncio.gather(
                *[asyncio.wait_for(poll_screen(snmp_engine, s, cfg), SCREEN_POLL_TIMEOUT) for s in screens],
                return_exceptions=True)
            for s, r in zip(screens, results):
                if isinstance(r, BaseException):
                    print(f"POLL: {s.get('name')} failed: {type(r).__name__}: {r}")

            valid_ids = {str(s['id']) for s in screens}
            for gid in [k for k in THEATERS_DATA if k not in valid_ids]:
                THEATERS_DATA.pop(gid, None)

            await broadcast_status()

            if time.time() - LAST_LIBRARY_UPDATE[0] > 600:
                LAST_LIBRARY_UPDATE[0] = time.time()
                asyncio.create_task(update_global_library())
        except Exception as e:
            print(f"Polling Loop Error: {e}")
        await asyncio.sleep(interval)


async def automation_loop():
    """Independent of poll duration so a slow IMS can't make a scheduled minute get skipped."""
    while True:
        try:
            await GLOBAL_AUTO_ENGINE.evaluate_rules()
        except Exception as e:
            print(f"Automation Loop Error: {e}")
        await asyncio.sleep(10)


# --- HANDLERS ---
class BaseHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        if CORS_ORIGIN:
            self.set_header("Access-Control-Allow-Origin", CORS_ORIGIN)
            self.set_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.set_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.set_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.set_header("X-Content-Type-Options", "nosniff")

    def options(self, *args):
        self.set_status(204)
        self.finish()

    def write_error(self, status_code, **kwargs):
        self.set_header("Content-Type", "application/json")
        self.finish(json.dumps({"status": "error", "error": self._reason, "code": status_code}))

    def json_body(self):
        try:
            body = json.loads(self.request.body or b'{}')
        except ValueError:
            raise tornado.web.HTTPError(400, "Invalid JSON body")
        if not isinstance(body, dict):
            raise tornado.web.HTTPError(400, "JSON object expected")
        return body

    def action(self, default):
        """Action from the URL path (/api/x/<action>) or ?action=, whichever is present."""
        last = self.request.path.rstrip('/').rsplit('/', 1)[-1]
        if last in ('add', 'update', 'delete', 'save', 'toggle', 'create'):
            return last
        return self.get_argument('action', default)

    def get_user(self, min_priv='Operator'):
        s = get_session(self.request.headers.get('Authorization'))
        if not s:
            self.set_status(401)
            self.write({"status": "error", "error": "Unauthorized", "code": 401})
            return None
        if PRIVILEGES.get(s['privilege'], 0) < PRIVILEGES[min_priv]:
            self.set_status(403)
            self.write({"status": "error", "error": "Forbidden", "code": 403})
            return None
        return s


class APIStatusHandler(BaseHandler):
    def get(self):
        if not self.get_user():
            return
        self.write(json.dumps(THEATERS_DATA))


class APIGdcStatusHandler(BaseHandler):
    async def get(self):
        if not self.get_user():
            return
        cfg = load_config() or {}
        ip = self.get_argument("ip", None)
        screen = find_screen_by_host(cfg, ip)
        if not screen:      # only configured devices - no arbitrary host probing
            self.set_status(404)
            return self.write({"status": "error", "error": "Unknown device"})
        user, pwd = server_creds(screen)
        status = await asyncio.to_thread(gdc_sr1000_client.get_sr1000_status, ip, user, pwd)
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(status))


class APIConfigHandler(BaseHandler):
    def get(self):
        if not self.get_user('Manager'):
            return
        cfg = load_config()
        if cfg is None:
            self.set_status(503)
            return self.write({"status": "error", "error": "Config temporarily unavailable"})
        safe = json.loads(json.dumps(cfg))
        for s in safe.get('screens', []):
            s['server_pass_set'] = bool(s.pop('server_pass', ''))   # never send device passwords to the browser
        self.write(json.dumps(safe))

    async def post(self):
        user = self.get_user('Admin')
        if not user:
            return
        params = self.json_body()
        action = self.action('update')
        cfg = load_config()
        if cfg is None:
            self.set_status(503)
            return self.write({"status": "error", "error": "Config temporarily unavailable"})
        cfg.setdefault('screens', [])

        if action == 'add':
            ip = str(params.get('ip', ''))
            if not HOST_RE.match(ip):
                return self.write({"status": "error", "error": "Invalid IP/host"})
            new_id = datetime.now().strftime("%Y%m%d%H%M%S%f")[:20]
            new_server = {"id": new_id, "name": str(params.get('name', 'New Theater'))[:64],
                          "projector_ip": ip, "ims_ip": ip}
            cfg['screens'].append(new_server)
            if not save_config(cfg):
                return self.write({"status": "error", "error": "Save failed"})
            audit_log(user['username'], "ADD_SCREEN", new_server['name'])
            self.write({"status": "ok", "id": new_id, "server": new_server})

        elif action == 'update':
            screen = find_screen(cfg, params.get('id'))
            if not screen:
                return self.write({"status": "error", "error": "Not Found"})
            fields = ['name', 'ims_ip', 'projector_ip', 'server_type', 'server_model',
                      'server_name', 'server_port', 'server_snmp_port', 'remote_mode', 'vnc_port',
                      'proj_type', 'proj_name', 'proj_port', 'proj_snmp_port',
                      'audio_type', 'audio_name', 'audio_ip', 'audio_port', 'audio_snmp_port',
                      'server_user', 'server_pass']
            for k in fields:
                if k not in params:
                    continue
                if k in ('ims_ip', 'projector_ip', 'audio_ip') and not HOST_RE.match(str(params[k])):
                    return self.write({"status": "error", "error": f"Invalid value for {k}"})
                if k == 'server_pass' and not params[k]:
                    continue   # the browser never receives the password, so blank means "unchanged"
                screen[k] = params[k]
            if not save_config(cfg):
                return self.write({"status": "error", "error": "Save failed"})
            audit_log(user['username'], "UPDATE_SCREEN", screen['name'])
            self.write({"status": "ok"})

        elif action == 'delete':
            self._delete(cfg, params.get('id'), user)
        else:
            self.write({"status": "error", "error": "Unknown action"})

    def _delete(self, cfg, s_id, user):
        if not s_id:
            return self.write({"status": "error", "error": "No ID provided"})
        sid = str(s_id)
        cfg['screens'] = [s for s in cfg.get('screens', []) if str(s['id']) != sid]
        if not save_config(cfg):
            return self.write({"status": "error", "error": "Save failed"})
        THEATERS_DATA.pop(sid, None)
        audit_log(user['username'], "DELETE_SCREEN", sid)
        self.write({"status": "ok"})

    async def delete(self):
        user = self.get_user('Admin')
        if not user:
            return
        cfg = load_config()
        if cfg is None:
            self.set_status(503)
            return self.write({"status": "error", "error": "Config temporarily unavailable"})
        self._delete(cfg, self.get_argument('id', None), user)


class APILoginHandler(BaseHandler):
    async def post(self):
        ip = self.request.remote_ip
        now = time.time()
        fails = LOGIN_FAILS.get(ip)
        if fails and fails[2] > now:
            self.set_status(429)
            return self.write({"status": "error", "error": "Too many attempts. Try again later."})

        params = self.json_body()
        username, password = str(params.get('username', '')), str(params.get('password', ''))
        users = read_json(USERS_FILE, []) or []
        user = next((u for u in users if u.get('username') == username), None)
        # Run the hash even for unknown users so timing doesn't reveal valid names.
        stored = user['password'] if user else hash_password("x")
        ok = await asyncio.to_thread(verify_password, password, stored)

        if not (user and ok):
            f = LOGIN_FAILS.setdefault(ip, [0, now, 0])
            if now - f[1] > LOGIN_LOCK_SECONDS:
                f[:] = [0, now, 0]
            f[0] += 1
            if f[0] >= LOGIN_MAX_FAILS:
                f[2] = now + LOGIN_LOCK_SECONDS
            audit_log(username or "UNKNOWN", "LOGIN_FAILED", ip)
            self.set_status(401)
            return self.write({"status": "error", "error": "Invalid credentials"})

        LOGIN_FAILS.pop(ip, None)
        if not user['password'].startswith("scrypt$"):   # upgrade legacy plaintext
            user['password'] = await asyncio.to_thread(hash_password, password)
            write_json(USERS_FILE, users)
        token = secrets.token_hex(32)
        SESSION_TOKENS[token] = {"id": user['id'], "username": user['username'], "privilege": user['privilege'],
                                 "created_at": now, "last_seen": now}
        audit_log(username, "LOGIN_SUCCESS", ip)
        self.write({"status": "ok", "user": {k: v for k, v in user.items() if k != 'password'}, "token": token})


class APILogoutHandler(BaseHandler):
    def post(self):
        token = self.request.headers.get('Authorization')
        s = SESSION_TOKENS.pop(token, None)
        if s:
            audit_log(s['username'], "LOGOUT")
        self.write({"status": "ok"})


class APILibraryHandler(BaseHandler):
    def get(self):
        if not self.get_user():
            return
        self.write(json.dumps(GLOBAL_LIBRARY))


class APISPLHandler(BaseHandler):
    async def get(self):
        if not self.get_user():
            return
        if self.get_argument('sub', None) == 'local' or self.request.path.endswith('/spl/local'):
            return self.write(json.dumps(read_json(SAVED_SPLS_FILE, []) or []))

        cfg = load_config() or {}
        target_ip = self.get_argument('host', None)
        if not target_ip and cfg.get('screens'):
            target_ip = screen_host(cfg['screens'][0])
        screen = find_screen_by_host(cfg, target_ip)
        if not screen:
            return self.write("[]")      # only configured devices
        try:
            if is_gdc(screen):
                user, pwd = server_creds(screen)
                spls = await asyncio.to_thread(gdc_sr1000_client.get_gdc_spl_list, target_ip, user, pwd)
            else:
                spls = await asyncio.to_thread(ims_soap_client.get_spl_list, target_ip)
        except Exception as e:
            print(f"SPL list error for {target_ip}: {e}")
            spls = []
        self.write(json.dumps(spls))

    async def post(self):
        user = self.get_user('Manager')
        if not user:
            return
        params = self.json_body()
        action = self.action('save')
        saved = read_json(SAVED_SPLS_FILE, []) or []

        if action == 'save':
            if not params.get('uuid'):
                return self.write({"status": "error", "error": "uuid required"})
            new_spl = {"uuid": params.get('uuid'), "title": params.get('title'), "duration": params.get('duration'),
                       "cpls": params.get('cpls', []), "saved_at": time.time()}
            idx = next((i for i, s in enumerate(saved) if s['uuid'] == new_spl['uuid']), -1)
            if idx >= 0:
                saved[idx] = new_spl
            else:
                saved.append(new_spl)
            ok = write_json(SAVED_SPLS_FILE, saved)
            self.write({"status": "ok" if ok else "error"})
        elif action == 'delete':
            saved = [s for s in saved if s['uuid'] != params.get('uuid')]
            ok = write_json(SAVED_SPLS_FILE, saved)
            self.write({"status": "ok" if ok else "error"})
        else:
            self.write({"status": "error", "error": "Unknown action"})


class APISPLCreateHandler(BaseHandler):
    async def post(self):
        user = self.get_user('Manager')
        if not user:
            return
        params = self.json_body()
        title, cpls, targets = params.get('title'), params.get('cpls', []), params.get('targets', [])
        if not title or not cpls or not targets:
            return self.write({"status": "error", "error": "Missing required fields"})

        screens = (load_config() or {}).get('screens', [])
        target_screens = [s for s in screens if s['name'] in targets]
        results = {"status": "ok", "success": [], "failed": []}

        for screen in target_screens:
            host = screen_host(screen)
            if not host:
                results["failed"].append({"screen": screen['name'], "error": "No IP configured"})
                continue
            if is_gdc(screen):
                results["failed"].append({"screen": screen['name'], "error": "SPL creation not supported on GDC"})
                continue
            try:
                res = await asyncio.to_thread(ims_soap_client.create_spl, host, title, cpls)
                if res.get('status') == 'ok':
                    results["success"].append(screen['name'])
                    audit_log(user['username'], "DISTRIBUTE_SPL", f"{title} -> {screen['name']}")
                else:
                    results["failed"].append({"screen": screen['name'], "error": res.get('error', 'Unknown Error')})
            except Exception as e:
                results["failed"].append({"screen": screen['name'], "error": str(e)})

        found = {s['name'] for s in target_screens}
        for t in targets:
            if t not in found:
                results["failed"].append({"screen": t, "error": "Screen not found in config"})
        self.write(json.dumps(results))


class APIAutomationHandler(BaseHandler):
    def get(self):
        if not self.get_user('Manager'):
            return
        self.write(json.dumps({"status": "ok", "rules": GLOBAL_AUTO_ENGINE.rules}))

    async def post(self):
        user = self.get_user('Manager')
        if not user:
            return
        action = self.action('save')
        raw = self.request.body
        params = self.json_body() if raw else {}
        engine = GLOBAL_AUTO_ENGINE

        if action == 'save':
            rule = params.get('rule')
            err = validate_rule(rule)
            if err:
                return self.write({"status": "error", "error": err})
            rule = {k: v for k, v in rule.items() if not k.startswith('_')}
            rule.setdefault('type', 'schedule')
            rule.setdefault('targets', 'all')
            rule['enabled'] = bool(rule.get('enabled', False))
            if not rule.get('id'):
                rule['id'] = f"rule-{secrets.token_hex(4)}"
            idx = next((i for i, r in enumerate(engine.rules) if r['id'] == rule['id']), -1)
            if idx >= 0:
                engine.rules[idx] = rule
            else:
                engine.rules.append(rule)
            engine.save_rules()
            audit_log(user['username'], "SAVE_AUTO_RULE", rule.get('name', rule['id']))
            self.write({"status": "ok", "rule": rule})

        elif action in ('delete', 'toggle'):
            r_id = params.get('id') or self.get_argument('id', None)    # frontend sends toggle id in the query
            if action == 'delete':
                engine.rules = [r for r in engine.rules if r['id'] != r_id]
                engine.save_rules()
                audit_log(user['username'], "DELETE_AUTO_RULE", r_id)
                return self.write({"status": "ok"})
            rule = next((r for r in engine.rules if r['id'] == r_id), None)
            if not rule:
                return self.write({"status": "error", "error": "Rule not found"})
            rule['enabled'] = not rule.get('enabled', False)
            engine.save_rules()
            audit_log(user['username'], "TOGGLE_AUTO_RULE", f"{r_id} -> {rule['enabled']}")
            self.write({"status": "ok", "enabled": rule['enabled']})
        else:
            self.write({"status": "error", "error": "Unknown action"})


class APIScheduleHandler(BaseHandler):
    async def get(self):
        if not self.get_user():
            return
        target_date = self.get_argument('date', None)
        if not target_date:
            return self.write({"error": "Missing date"})

        async def one(s):
            if is_gdc(s) or not screen_host(s):
                return []
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(ims_soap_client.get_schedule_list, screen_host(s), target_date), 20)
            except Exception:
                return []

        screens = (load_config() or {}).get('screens', [])
        results = await asyncio.gather(*[one(s) for s in screens])
        self.write(json.dumps({s['id']: {"id": s['id'], "name": s['name'], "schedules": r}
                               for s, r in zip(screens, results)}))

    async def post(self):
        user = self.get_user('Manager')
        if not user:
            return
        params = self.json_body()
        screen_id, spl_uuid, start_time = params.get('screen_id'), params.get('spl_uuid'), params.get('start_time')
        if not screen_id or not spl_uuid or not start_time:
            return self.write({"status": "error", "error": "Missing required fields"})
        screen = find_screen(load_config(), screen_id)
        if not screen:
            return self.write({"status": "error", "error": "Screen not found"})
        if is_gdc(screen):
            return self.write({"status": "error", "error": "Scheduling not supported on GDC"})
        try:
            res = await asyncio.to_thread(ims_soap_client.create_schedule, screen_host(screen), spl_uuid, start_time)
        except Exception as e:
            return self.write({"status": "error", "error": str(e)})
        if res.get('status') == 'ok':
            audit_log(user['username'], "ADD_SCHEDULE", f"{screen['name']} - {str(spl_uuid)[:8]} @ {start_time}")
            self.write({"status": "ok", "id": res.get('id')})
        else:
            self.write({"status": "error", "error": res.get('error', 'Unknown Error')})


class APITheaterPlaylistHandler(BaseHandler):
    async def get(self):
        if not self.get_user():
            return
        t_id = self.get_argument('id', None)
        if not t_id:
            return self.write({"error": "Missing ID"})
        screen = find_screen(load_config(), t_id)
        if not screen:
            return self.write({"error": "Not Found"})

        host = screen_host(screen)
        status_data = THEATERS_DATA.get(str(t_id), {})
        spl_id = status_data.get('splId')
        items, active_idx = [], 0

        if spl_id:
            active_idx = status_data.get('elementIndex', 0)
            try:
                if is_gdc(screen):
                    user, pwd = server_creds(screen)
                    items = await asyncio.to_thread(gdc_sr1000_client.get_gdc_spl_content_detailed, host, user, pwd, spl_id)
                else:
                    items = await asyncio.to_thread(ims_soap_client.get_spl_content_detailed, host, spl_id)

                # Active item from SPL position: item i spans [sum, sum+duration)
                spl_pos, acc = status_data.get('splPositionSec', 0), 0
                for i, item in enumerate(items):
                    dur = item.get('duration', 0)
                    if acc <= spl_pos < acc + dur:
                        active_idx = i
                        break
                    acc += dur
            except Exception as e:
                print(f"API ERROR: SPL content for {spl_id}: {e}")

        self.write(json.dumps({"splId": spl_id, "activeCplId": status_data.get('cplId'),
                               "activeElementIndex": active_idx, "items": items}))


class APITheaterLoadHandler(BaseHandler):
    async def post(self):
        user = self.get_user('Manager')
        if not user:
            return
        t_id, spl_uuid = self.get_argument('id', None), self.get_argument('spl', None)
        if not t_id or not spl_uuid:
            return self.write({"status": "error", "error": "Missing ID or SPL"})
        screen = find_screen(load_config(), t_id)
        if not screen:
            return self.write({"status": "error", "error": "Screen not found"})
        if is_gdc(screen):
            return self.write({"status": "error", "error": "Loading SPL not supported on GDC"})
        try:
            result = await asyncio.to_thread(ims_soap_client.load_spl, screen_host(screen), spl_uuid)
            audit_log(user['username'], "LOAD_SPL", f"{screen['name']} - {spl_uuid[:8]}")
            self.write(json.dumps(result))
        except Exception as e:
            self.write({"status": "error", "error": str(e)})


class APIControlHandler(BaseHandler):
    async def post(self):
        user = self.get_user('Manager')
        if not user:
            return
        params = self.json_body()
        cfg = load_config()
        # Devices are resolved from config only - the client can't point commands at arbitrary hosts.
        screen = find_screen(cfg, params.get('id')) or find_screen_by_host(cfg, params.get('host'))
        if not screen or not screen_host(screen):
            return self.write({"status": "error", "error": "Unknown device"})
        if is_gdc(screen):
            return self.write({"status": "error", "error": "Remote control not supported on GDC"})

        cmd = params.get('command')
        if cmd not in CONTROL_COMMANDS:
            return self.write({"status": "error", "error": "Unknown command"})
        host = screen_host(screen)
        audit_log(user['username'], f"CONTROL_{cmd}", f"{screen['name']} ({host})")
        try:
            if cmd == 'load_spl':
                res = await asyncio.to_thread(ims_soap_client.load_spl_to_ims, host, params.get('uuid'))
            else:
                res = await asyncio.to_thread(ims_soap_client.send_command, host, cmd)
        except Exception as e:
            res = {"status": "error", "error": str(e)}
        self.write(json.dumps(res))


class APIUsersHandler(BaseHandler):
    @staticmethod
    def _public(u):
        return {k: v for k, v in u.items() if k != 'password'}

    def get(self):
        if not self.get_user('Admin'):
            return
        users = read_json(USERS_FILE, []) or []
        self.write(json.dumps({'status': 'ok', 'users': [self._public(u) for u in users]}))

    async def post(self):
        user = self.get_user('Admin')
        if not user:
            return
        params = self.json_body()
        action = self.action('add')
        users = read_json(USERS_FILE, []) or []
        admins = lambda lst: [u for u in lst if u.get('privilege') == 'Admin']

        if action == 'add':
            username, password = str(params.get('username', '')), str(params.get('password', ''))
            priv = params.get('privilege', 'Operator')
            if not USERNAME_RE.match(username):
                return self.write({"status": "error", "error": "Username must be 3-32 chars (letters, digits, . _ -)"})
            if len(password) < 8:
                return self.write({"status": "error", "error": "Password must be at least 8 characters"})
            if priv not in PRIVILEGES:
                return self.write({"status": "error", "error": "Invalid privilege"})
            if any(u['username'].lower() == username.lower() for u in users):
                return self.write({"status": "error", "error": "Username already exists"})
            nums = [int(m.group(1)) for u in users if (m := re.match(r'USR-(\d+)$', str(u.get('id'))))]
            new_user = {"id": f"USR-{(max(nums) + 1 if nums else 1):03d}", "username": username,
                        "email": str(params.get('email', ''))[:128], "password": await asyncio.to_thread(hash_password, password),
                        "privilege": priv}
            users.append(new_user)
            write_json(USERS_FILE, users)
            audit_log(user['username'], "ADD_USER", username)
            self.write({"status": "ok", "user": self._public(new_user)})

        elif action == 'update':
            target = next((u for u in users if u['id'] == params.get('id')), None)
            if not target:
                return self.write({"status": "error", "error": "User not found"})
            if 'username' in params:
                if not USERNAME_RE.match(str(params['username'])) or any(
                        u is not target and u['username'].lower() == params['username'].lower() for u in users):
                    return self.write({"status": "error", "error": "Invalid or duplicate username"})
                target['username'] = params['username']
            if 'email' in params:
                target['email'] = str(params['email'])[:128]
            if 'privilege' in params:
                if params['privilege'] not in PRIVILEGES:
                    return self.write({"status": "error", "error": "Invalid privilege"})
                if target['privilege'] == 'Admin' and params['privilege'] != 'Admin' and len(admins(users)) <= 1:
                    return self.write({"status": "error", "error": "Cannot demote the last Admin"})
                target['privilege'] = params['privilege']
            if params.get('password'):
                if len(str(params['password'])) < 8:
                    return self.write({"status": "error", "error": "Password must be at least 8 characters"})
                target['password'] = await asyncio.to_thread(hash_password, str(params['password']))
            write_json(USERS_FILE, users)
            revoke_sessions(target['id'])      # re-login picks up new privilege/password
            audit_log(user['username'], "UPDATE_USER", target['username'])
            self.write({"status": "ok"})

        elif action == 'delete':
            target = next((u for u in users if u['id'] == params.get('id')), None)
            if not target:
                return self.write({"status": "error", "error": "User not found"})
            if target['id'] == user['id']:
                return self.write({"status": "error", "error": "You cannot delete your own account"})
            if target['privilege'] == 'Admin' and len(admins(users)) <= 1:
                return self.write({"status": "error", "error": "Cannot delete the last Admin"})
            write_json(USERS_FILE, [u for u in users if u is not target])
            revoke_sessions(target['id'])
            audit_log(user['username'], "DELETE_USER", target['username'])
            self.write({"status": "ok"})
        else:
            self.write({"status": "error", "error": "Unknown action"})


class NoCacheStaticFileHandler(tornado.web.StaticFileHandler):
    def set_extra_headers(self, path):
        self.set_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.set_header("Pragma", "no-cache")
        self.set_header("Expires", "0")


class TMSWebSocket(tornado.websocket.WebSocketHandler):
    """Same-origin only (tornado default). Client must send {"type":"auth","token":...} within 10 s."""
    token = None

    def open(self):
        self._auth_timer = tornado.ioloop.IOLoop.current().call_later(10, lambda: self.close(4401, "Auth timeout"))

    async def on_message(self, message):
        try:
            msg = json.loads(message)
        except ValueError:
            return
        if self.token or not isinstance(msg, dict) or msg.get('type') != 'auth':
            return
        if not get_session(msg.get('token')):
            return self.close(4401, "Unauthorized")
        self.token = msg['token']
        tornado.ioloop.IOLoop.current().remove_timeout(self._auth_timer)
        WS_CLIENTS.add(self)
        await self.write_message(json.dumps({"type": "status", "data": THEATERS_DATA}))

    def on_close(self):
        WS_CLIENTS.discard(self)


def make_app():
    return tornado.web.Application([
        (r"/api/status", APIStatusHandler),
        (r"/api/gdc/status", APIGdcStatusHandler),
        (r"/api/config", APIConfigHandler),
        (r"/api/config/(?:add|update|delete)", APIConfigHandler),
        (r"/api/library", APILibraryHandler),
        (r"/api/login", APILoginHandler),
        (r"/api/logout", APILogoutHandler),
        (r"/api/spl/(?:local|save|delete)", APISPLHandler),
        (r"/api/spl/create", APISPLCreateHandler),
        (r"/api/spls?", APISPLHandler),
        (r"/api/schedule(?:/add)?", APIScheduleHandler),
        (r"/api/theater/playlist", APITheaterPlaylistHandler),
        (r"/api/theater/load", APITheaterLoadHandler),
        (r"/api/control", APIControlHandler),
        (r"/api/automation(?:/(?:save|delete|toggle))?", APIAutomationHandler),
        (r"/api/users(?:/(?:add|update|delete))?", APIUsersHandler),
        (r"/ws", TMSWebSocket),
        (r"/(.*)", NoCacheStaticFileHandler, {"path": FRONTEND_DIR, "default_filename": "index.html"}),
    ])


async def main():
    import subprocess
    ensure_users()

    vnc_proc = None
    vnc_proxy_script = os.path.join(BASE_DIR, 'vnc_proxy.py')
    if os.path.exists(vnc_proxy_script):
        print(f"INFO: Starting VNC Middleware ({vnc_proxy_script})...")
        vnc_proc = subprocess.Popen([sys.executable, vnc_proxy_script], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
    else:
        print("WARNING: VNC Proxy script not found. VNC features will fail gracefully.")

    server = tornado.httpserver.HTTPServer(make_app())
    server.listen(PORT, address=BIND_HOST)
    print(f"SUCCESS: TMS Portal (Real-Time) running at http://localhost:{PORT}")

    tasks = [asyncio.create_task(tms_polling_loop()), asyncio.create_task(automation_loop())]
    try:
        await asyncio.Event().wait()
    finally:
        for t in tasks:
            t.cancel()
        if vnc_proc:
            vnc_proc.terminate()


def run_server():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run_server()
