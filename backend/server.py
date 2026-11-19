from datetime import datetime
import tornado.ioloop
import tornado.web
import tornado.websocket
import tornado.httpserver
import secrets
import os
import sys
import json
import re
import urllib.parse
import time
import asyncio

# --- CONFIGURATION ---
PORT = 5050
CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
FRONTEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '../frontend'))
VALID_OIDS_FILE = os.path.join(os.path.dirname(__file__), 'valid_oids.json')
SAVED_SPLS_FILE = os.path.join(os.path.dirname(__file__), 'saved_spls.json')
AUTOMATION_RULES_FILE = os.path.join(os.path.dirname(__file__), 'automation_rules.json')

DEFAULT_SERVER_PASS = os.environ.get('TMS_DEFAULT_SERVER_PASS', '')

DEFAULT_CONFIG = {
    "screens": [],
    "port": 161,
    "community": "public"
}

# Global State
THEATERS_DATA = {}
GLOBAL_LIBRARY = {}
LIBRARY_LOCK = asyncio.Lock()
WS_CLIENTS = set()
LAST_LIBRARY_UPDATE = [0]  # Mutable for closure access

def load_config():
    if os.path.exists(CONFIG_FILE_PATH):
        try:
            with open(CONFIG_FILE_PATH, 'r') as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except: 
            # Transient error (lock, race), do not return default as it wipes data
            return None
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    try:
        # Atomic Write Pattern: Write to temp, then rename
        tmp_file = CONFIG_FILE_PATH + ".tmp"
        with open(tmp_file, 'w') as f:
            json.dump(cfg, f, indent=4)
        
        # Verify tmp file exists and has content before renaming (extra safety)
        if os.path.exists(tmp_file) and os.path.getsize(tmp_file) > 0:
            os.replace(tmp_file, CONFIG_FILE_PATH)
            return True
        return False
    except: return False

# --- SNMP IMPORTS ---
try:
    from pysnmp.hlapi.asyncio import get_cmd, SnmpEngine, CommunityData, UdpTransportTarget, ContextData, ObjectType, ObjectIdentity
    PYSNMP_AVAILABLE = True
except ImportError:
    PYSNMP_AVAILABLE = False

# --- GLOBAL STATE ---
THEATERS_DATA = {} # Store status per theater ID
GLOBAL_LIBRARY = [] # Aggregated CPLs
LIBRARY_LOCK = asyncio.Lock()
SHARED_SNMP_ENGINE = None
SESSION_TOKENS = {} # token -> user_object
WS_CLIENTS = set()
LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')
AUDIT_LOG_FILE = os.path.join(LOG_DIR, 'audit.log')

# Ensure logs dir exists
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

def audit_log(username, action, details=""):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] User: {username} | Action: {action} | Details: {details}\n"
    try:
        with open(AUDIT_LOG_FILE, 'a') as f:
            f.write(entry)
    except: pass
    print(f"📝 AUDIT: {entry.strip()}")

# --- TMS ENGINE ---
import ims_soap_client

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '../server_status_methods'))
import gdc_sr1000_client

async def poll_screen(snmp_engine, screen, cfg):
    s_id = screen['id']
    p_ip = screen['projector_ip']
    ims_ip = screen.get('ims_ip', p_ip)
    
    data = THEATERS_DATA.get(s_id, {
        "status": "Offline", "lamp": "OFF", "playback": "Stopped",
        "content": "No Data", "progress": 0, "remaining": "--:--",
        "temp": "0°C", "storage": "0%", "errors": []
    })
    # Merge all config fields so frontend doesn't lose them
    for k, v in screen.items():
        data[k] = v
    if 'ip' not in data: data['ip'] = p_ip

    # 1. Projector Health via SNMP
    if p_ip and p_ip not in ["0.0.0.0", ""]:
        try:
            transport = await UdpTransportTarget.create((p_ip, 161), timeout=0.3, retries=0)
            ei, es, eidx, vbs = await get_cmd(snmp_engine, CommunityData(cfg.get('community', 'public')), transport, ContextData(), 
                                            ObjectType(ObjectIdentity('1.3.6.1.2.1.1.1.0')))
            
            if not ei and not es:
                data["status"] = "Online"
            else:
                data["status"] = "Offline"
        except Exception:
            data["status"] = "Offline"
    else:
        data["status"] = "Offline"

    # 2. IMS Health via SOAP/REST (Independent of Projector)
    server_type = screen.get("server_type", "Dolby")
    server_user = screen.get("server_user", "Maintenance")
    server_pass = screen.get("server_pass", DEFAULT_SERVER_PASS)
    
    if ims_ip and ims_ip not in ["0.0.0.0", ""]:
        try:
            if server_type == "GDC":
                host_str = f"{ims_ip}:{screen.get('server_port', 80)}" if screen.get('server_port') else ims_ip
                ims_status = await asyncio.to_thread(gdc_sr1000_client.get_sr1000_status, host_str, server_user, server_pass)
            else:
                ims_status = await asyncio.to_thread(ims_soap_client.get_status_data, ims_ip) 
            
            if ims_status and ims_status.get("connected"):
                data["status"] = "Online" # Force online if IMS responds
                data["playback"] = ims_status.get("playbackStatus", "Stopped")
                data["spl"] = ims_status.get("spl", "-")
                data["splId"] = ims_status.get("splId")
                data["content"] = ims_status.get("content", "No Content Loaded")
                data["cplId"] = ims_status.get("cplId")
                data["elementIndex"] = ims_status.get("elementIndex", 0)
                data["progress"] = ims_status.get("positionSec", 0)
                dur = ims_status.get("durationSec", 1)
                data["progress_pct"] = int((data["progress"] / dur) * 100) if dur > 0 else 0
                data["remaining"] = ims_status.get("duration", "--:--")
                data["lamp"] = "ON" if data["playback"] == "Playing" else "OFF"
                data["storage"] = ims_status.get("storage", "0%")
                data["splPositionSec"] = ims_status.get("splPositionSec", 0)
                
                if server_type == "GDC":
                    data["schedules"] = []
                else:
                    now = time.time()
                    last_sched = data.get("_last_sched_fetch", 0)
                    # Reduced pressure: only fetch schedules if manually requested or every 5 mins
                    if now - last_sched > 300: 
                        try:
                            data["schedules"] = await asyncio.to_thread(ims_soap_client.get_schedule_list, ims_ip)
                            data["_last_sched_fetch"] = now
                        except:
                            data["schedules"] = data.get("schedules", [])
            else:
                # If IMS is offline, playback status depends on Projector status
                data["playback"] = "Offline" if data["status"] == "Offline" else "Stopped"
                data["content"] = "No Data" if data["status"] == "Offline" else "No Content"
        except:
             data["playback"] = "Offline"
             data["schedules"] = []
    else:
        data["playback"] = "Offline"
        data["content"] = "No Data"
        data["schedules"] = []

    # Final check: Ensure screen hasn't been deleted while we were polling
    try:
        current_cfg = load_config()
        if any(s['id'] == s_id for s in current_cfg.get('screens', [])):
            THEATERS_DATA[s_id] = data
    except: pass

# --- AUTOMATION ENGINE (Step 5) ---
class AutomationEngine:
    def __init__(self):
        self.rules = []
        self.load_rules()

    def load_rules(self):
        if os.path.exists(AUTOMATION_RULES_FILE):
            try:
                with open(AUTOMATION_RULES_FILE, 'r') as f:
                    self.rules = json.load(f)
            except:
                self.rules = []
        else:
            # Default example rules
            self.rules = [
                {
                    "id": "rule-001",
                    "name": "Evening Shutdown",
                    "type": "schedule",
                    "time": "23:00",
                    "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                    "action": "POWER_OFF",
                    "targets": "all",
                    "enabled": False
                }
            ]
            self.save_rules()

    def save_rules(self):
        try:
            with open(AUTOMATION_RULES_FILE, 'w') as f:
                json.dump(self.rules, f, indent=4)
        except: pass

    async def evaluate_rules(self):
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_day = now.strftime("%a")

        for rule in self.rules:
            if not rule.get('enabled', False): continue

            # Schedule Based Rules
            if rule.get('type') == 'schedule':
                if rule.get('time') == current_time and current_day in rule.get('days', []):
                    # Check if already triggered this minute to avoid loops
                    if rule.get('_last_trigger') == current_time: continue
                    rule['_last_trigger'] = current_time
                    
                    print(f"AUTO: Triggering rule '{rule['name']}' ({rule['action']})")
                    await self.execute_action(rule['action'], rule.get('targets'))

    async def execute_action(self, action, targets):
        cfg = load_config()
        if not cfg: return
        
        screens = cfg.get('screens', [])
        if targets != 'all':
            target_ids = targets if isinstance(targets, list) else [targets]
            screens = [s for s in screens if s['id'] in target_ids]

        for screen in screens:
            host = screen.get('ims_ip', screen['projector_ip'])
            try:
                if action == 'POWER_ON':
                    await asyncio.to_thread(ims_soap_client.send_command, host, 'power_on')
                elif action == 'POWER_OFF':
                    await asyncio.to_thread(ims_soap_client.send_command, host, 'power_off')
                audit_log("SYSTEM_AUTO", f"AUTO_{action}", f"Target: {screen['name']} ({host})")
            except Exception as e:
                print(f"ERROR: Automation Error for {screen['name']}: {e}")

GLOBAL_AUTO_ENGINE = AutomationEngine()

async def update_global_library():
    global GLOBAL_LIBRARY
    async with LIBRARY_LOCK:
        cfg = load_config()
        new_library = {}
        def fetch_all():
            for screen in cfg.get('screens', []):
                ims_ip = screen.get('ims_ip', screen['projector_ip'])
                try:
                    cpls = ims_soap_client.get_cpl_list(ims_ip)
                    kdms = ims_soap_client.get_kdm_list(ims_ip)
                    for c in cpls:
                        uuid = c['uuid']
                        is_encrypted = c.get('encrypted', True)
                        raw_stat = kdms.get(uuid, "Missing")
                        kdm_stat = "Free" if not is_encrypted else raw_stat
                        if uuid not in new_library:
                            new_library[uuid] = {**c, "screens": [screen['name']], "kdm": kdm_stat}
                        else:
                            if screen['name'] not in new_library[uuid]["screens"]:
                                new_library[uuid]["screens"].append(screen['name'])
                except: continue
        try:
            print("LIBRARY: Syncing global library from screens...")
            await asyncio.to_thread(fetch_all)
            GLOBAL_LIBRARY = list(new_library.values())
            print(f"SUCCESS: LIBRARY: Syncing complete. {len(GLOBAL_LIBRARY)} items in global list.")
        except Exception as e:
            print(f"ERROR: LIBRARY: Syncing failed: {e}")

# --- BROADCAST SYSTEM ---
def broadcast_status(data):
    if not WS_CLIENTS: return
    msg = json.dumps({"type": "status", "data": data})
    # Tornado needs thread-safe way to call write_message if this is from another thread
    # Since we are using asyncio loop, we can use IOLoop.current().add_callback
    loop = tornado.ioloop.IOLoop.current()
    for client in list(WS_CLIENTS):
        try:
            loop.add_callback(client.write_message, msg)
        except: pass

async def tms_polling_loop():
    global SHARED_SNMP_ENGINE
    if SHARED_SNMP_ENGINE is None: SHARED_SNMP_ENGINE = SnmpEngine()
    last_lib_update = time.time() # Start timer from now to avoid double sync
    asyncio.create_task(update_global_library())
    while True:
        cfg = load_config()
        if cfg is None:
            await asyncio.sleep(1)
            continue
            
        now = time.time()
        
        # --- EXECUTE POLLING AT START OF LOOP ---
        tasks = [poll_screen(SHARED_SNMP_ENGINE, s, cfg) for s in cfg.get('screens', [])]
        if tasks: 
            await asyncio.gather(*tasks)
            # Push updates to connected WebSockets
            broadcast_status(THEATERS_DATA)

        # --- GHOST GARBAGE COLLECTION ---
        valid_ids = [str(s['id']) for s in cfg.get('screens', [])]
        ghost_ids = [k for k in THEATERS_DATA.keys() if k not in valid_ids]
        for gid in ghost_ids:
            try: del THEATERS_DATA[gid]
            except: pass
        # -------------------------------

        # --- EVALUATE AUTOMATION ---
        try:
            await GLOBAL_AUTO_ENGINE.evaluate_rules()
        except: pass
        # ---------------------------

        if now - last_lib_update > 600: # Sync every 10 minutes instead of 5
            asyncio.create_task(update_global_library())
            last_lib_update = now
            
        await asyncio.sleep(60) # Poll screens every 60 seconds (Standard/Legal)

# --- TORNADO HANDLERS ---
import tornado.web
import tornado.websocket
import tornado.httpserver
import tornado.ioloop
import secrets

class BaseHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.set_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.set_header("Cache-Control", "no-cache, no-store, must-revalidate")

    def options(self, *args):
        self.set_status(204)
        self.finish()

    def get_user(self, min_priv='Operator'):
        token = self.request.headers.get('Authorization')
        print(f"DEBUG: Auth Check - Path: {self.request.path}, Token: {token[:10] if token else 'NONE'}...")
        if not token or token not in SESSION_TOKENS:
            print("DEBUG: Auth Failed - Invalid Token")
            self.set_status(401)
            self.write({"status": "error", "error": "Unauthorized", "code": 401})
            return None
        
        user = SESSION_TOKENS[token]
        print(f"DEBUG: Auth Success - User: {user['username']}, Priv: {user['privilege']}")
        levels = {'Operator': 1, 'Manager': 2, 'Admin': 3}
        if levels.get(user['privilege'], 0) < levels.get(min_priv, 1):
            print(f"DEBUG: Auth Failed - Insufficient Privileges. Required: {min_priv}")
            self.set_status(403)
            self.write({"status": "error", "error": "Forbidden", "code": 403})
            return None
        return user

class APIStatusHandler(BaseHandler):
    def get(self):
        if not self.get_user(): return
        self.write(json.dumps(THEATERS_DATA))

class APIGdcStatusHandler(tornado.web.RequestHandler):
    async def get(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Content-Type", "application/json")
        ip = "192.168.11.63"
        user = "Maintenance"
        pwd = DEFAULT_SERVER_PASS
        param_ip = self.get_argument("ip", None)
        if param_ip:
            ip = param_ip
            try:
                cfg = load_config()
                screen = next((s for s in cfg['screens'] if s.get('ims_ip') == ip or s.get('projector_ip') == ip), None)
                if screen:
                    user = screen.get('server_user', user)
                    pwd = screen.get('server_pass', pwd)
            except:
                pass
        status = await asyncio.to_thread(
            gdc_sr1000_client.get_sr1000_status, ip, user, pwd
        )
        self.write(json.dumps(status))

class APIConfigHandler(BaseHandler):
    def get(self):
        if not self.get_user('Manager'): return
        self.write(json.dumps(load_config()))

    async def post(self):
        user = self.get_user('Admin')
        if not user: return
        try:
            params = json.loads(self.request.body)
            
            # Detect action from URL path or query parameter
            path = self.request.path
            if path.endswith('/add'):
                action = 'add'
            elif path.endswith('/update'):
                action = 'update'
            elif path.endswith('/delete'):
                action = 'delete'
            else:
                action = self.get_argument('action', 'update')
            
            cfg = load_config()
            print(f"DEBUG: Config Request - Action: {action}, ID: {params.get('id')}")
            
            if action == 'add':
                new_id = datetime.now().strftime("%Y%m%d%H%M%S")
                new_server = { "id": new_id, "name": params.get('name', 'New Theater'), "projector_ip": params.get('ip', ''), "ims_ip": params.get('ip', '') }
                cfg['screens'].append(new_server)
                save_config(cfg)
                audit_log(user['username'], "ADD_SCREEN", new_server['name'])
                self.write(json.dumps({"status": "ok", "id": new_id, "server": new_server}))
            
            elif action == 'update':
                screen = next((s for s in cfg['screens'] if s['id'] == str(params.get('id'))), None)
                print(f"DEBUG: Update Request - Found Screen: {screen['name'] if screen else 'NONE'}")
                if screen:
                    # Comprehensive field list for full auditorium configuration
                    fields = [
                        'name', 'ims_ip', 'projector_ip', 'server_type', 'server_model',
                        'server_name', 'server_port', 'server_snmp_port', 'remote_mode', 'vnc_port',
                        'proj_type', 'proj_name', 'proj_port', 'proj_snmp_port',
                        'audio_type', 'audio_name', 'audio_ip', 'audio_port', 'audio_snmp_port',
                        'server_user', 'server_pass'
                    ]
                    for k in fields:
                        if k in params: screen[k] = params[k]
                    save_config(cfg)
                    audit_log(user['username'], "UPDATE_SCREEN", screen['name'])
                    self.write(json.dumps({"status": "ok"}))
                else: self.write(json.dumps({"status": "error", "error": "Not Found"}))

            elif action == 'delete':
                s_id = params.get('id')
                if s_id:
                    s_id_str = str(s_id)
                    cfg = load_config()
                    cfg['screens'] = [s for s in cfg['screens'] if str(s['id']) != s_id_str]
                    save_config(cfg)
                    if s_id_str in THEATERS_DATA:
                        del THEATERS_DATA[s_id_str]
                    audit_log(user['username'], "DELETE_SCREEN", s_id_str)
                    self.write(json.dumps({"status": "ok"}))
                else:
                    self.write(json.dumps({"status": "error", "error": "No ID provided"}))
        except Exception as e: self.write(json.dumps({"status": "error", "error": str(e)}))

    async def delete(self):
        user = self.get_user('Admin')
        if not user: return
        s_id = self.get_argument('id', None)
        if s_id:
            cfg = load_config()
            cfg['screens'] = [s for s in cfg['screens'] if s['id'] != s_id]
            save_config(cfg)
            if s_id in THEATERS_DATA: del THEATERS_DATA[s_id]
            audit_log(user['username'], "DELETE_SCREEN", s_id)
            self.write(json.dumps({"status": "ok"}))
        else: self.write(json.dumps({"status": "error", "error": "No ID"}))

class APILoginHandler(BaseHandler):
    def post(self):
        try:
            params = json.loads(self.request.body)
            username = params.get('username')
            password = params.get('password')
            users_file = os.path.join(os.path.dirname(__file__), 'users.json')
            users = []
            if os.path.exists(users_file):
                with open(users_file, 'r') as f: users = json.load(f)
            user = next((u for u in users if u['username'] == username and u['password'] == password), None)
            if user:
                token = secrets.token_hex(16)
                SESSION_TOKENS[token] = { "id": user['id'], "username": user['username'], "privilege": user['privilege'], "created_at": time.time() }
                audit_log(username, "LOGIN_SUCCESS")
                self.write(json.dumps({"status": "ok", "user": {k:v for k,v in user.items() if k != 'password'}, "token": token}))
            else:
                audit_log(username or "UNKNOWN", "LOGIN_FAILED")
                self.write(json.dumps({"status": "error", "error": "Invalid credentials"}))
        except Exception as e: self.write(json.dumps({"status": "error", "error": str(e)}))

class APILogoutHandler(BaseHandler):
    def post(self):
        token = self.request.headers.get('Authorization')
        if token in SESSION_TOKENS:
            user = SESSION_TOKENS[token]
            audit_log(user['username'], "LOGOUT")
            del SESSION_TOKENS[token]
        self.write(json.dumps({"status": "ok"}))

class APILibraryHandler(BaseHandler):
    def get(self):
        if not self.get_user(): return
        print(f"DEBUG: APILibraryHandler GET - Serving {len(GLOBAL_LIBRARY)} items")
        self.write(json.dumps(GLOBAL_LIBRARY))

class APISPLHandler(BaseHandler):
    def get(self):
        if not self.get_user(): return
        sub = self.get_argument('sub', None)
        if sub == 'local' or self.request.path.endswith('/spl/local'):
            try:
                with open(SAVED_SPLS_FILE, 'r') as f: self.write(json.dumps(json.load(f)))
            except: self.write("[]")
        else:
            target_ip = self.get_argument('host', None)
            if not target_ip:
                cfg = load_config(); screens = cfg.get('screens', [])
                if screens: target_ip = screens[0].get('ims_ip', screens[0]['projector_ip'])
            print(f"DEBUG: APISPLHandler GET - Fetching SPLs for {target_ip}")
            spls = []
            if target_ip:
                cfg = load_config()
                screen = next((s for s in cfg['screens'] if s.get('ims_ip') == target_ip or s.get('projector_ip') == target_ip), None)
                if screen and screen.get('server_type') == 'GDC':
                    user = screen.get('server_user', 'Maintenance')
                    pwd = screen.get('server_pass', DEFAULT_SERVER_PASS)
                    spls = gdc_sr1000_client.get_gdc_spl_list(target_ip, user, pwd)
                else:
                    spls = ims_soap_client.get_spl_list(target_ip)
            print(f"DEBUG: APISPLHandler GET - Found {len(spls)} SPLs")
            self.write(json.dumps(spls))

    async def post(self):
        user = self.get_user('Manager')
        if not user: return
        params = json.loads(self.request.body)
        action = self.get_argument('action', 'save')
        
        if action == 'save':
            saved = []
            try:
                with open(SAVED_SPLS_FILE, 'r') as f: saved = json.load(f)
            except: pass
            new_spl = { "uuid": params.get('uuid'), "title": params.get('title'), "duration": params.get('duration'), "cpls": params.get('cpls', []), "saved_at": time.time() }
            idx = next((i for i, s in enumerate(saved) if s['uuid'] == new_spl['uuid']), -1)
            if idx >= 0: saved[idx] = new_spl
            else: saved.append(new_spl)
            with open(SAVED_SPLS_FILE, 'w') as f: json.dump(saved, f, indent=2)
            self.write({"status": "ok"})
        
        elif action == 'delete':
            uuid = params.get('uuid')
            try:
                with open(SAVED_SPLS_FILE, 'r') as f: saved = json.load(f)
                saved = [s for s in saved if s['uuid'] != uuid]
                with open(SAVED_SPLS_FILE, 'w') as f: json.dump(saved, f, indent=2)
                self.write({"status": "ok"})
            except: self.write({"status": "error"})

class APISPLCreateHandler(BaseHandler):
    async def post(self):
        user = self.get_user('Manager')
        if not user: return
        
        try:
            params = json.loads(self.request.body)
            title = params.get('title')
            cpls = params.get('cpls', [])
            targets = params.get('targets', [])
            
            if not title or not cpls or not targets:
                self.write(json.dumps({"status": "error", "error": "Missing required fields"}))
                return

            cfg = load_config()
            screens = cfg.get('screens', [])
            
            results = {"status": "ok", "success": [], "failed": []}
            
            # Map targets to IPs
            target_screens = [s for s in screens if s['name'] in targets]
            
            for screen in target_screens:
                host = screen.get('ims_ip', screen.get('projector_ip'))
                if not host:
                    results["failed"].append({"screen": screen['name'], "error": "No IP configured"})
                    continue
                
                # Execute in thread to avoid blocking main loop
                try:
                    res = await asyncio.to_thread(ims_soap_client.create_spl, host, title, cpls)
                    if res.get('status') == 'ok':
                        results["success"].append(screen['name'])
                        audit_log(user['username'], "DISTRIBUTE_SPL", f"{title} -> {screen['name']}")
                    else:
                        results["failed"].append({"screen": screen['name'], "error": res.get('error', 'Unknown Error')})
                except Exception as e:
                    results["failed"].append({"screen": screen['name'], "error": str(e)})

            # Check for missing targets
            found_names = [s['name'] for s in target_screens]
            for t in targets:
                if t not in found_names:
                    results["failed"].append({"screen": t, "error": "Screen not found in config"})

            self.write(json.dumps(results))

        except Exception as e:
            self.write(json.dumps({"status": "error", "error": str(e)}))

class APIAutomationHandler(BaseHandler):
    def get(self):
        if not self.get_user('Manager'): return
        self.write(json.dumps({"status": "ok", "rules": GLOBAL_AUTO_ENGINE.rules}))

    async def post(self):
        user = self.get_user('Manager')
        if not user: return
        try:
            params = json.loads(self.request.body)
            action = self.get_argument('action', 'save')

            if action == 'save':
                rule = params.get('rule')
                if not rule.get('id'):
                    rule['id'] = f"rule-{secrets.token_hex(4)}"
                
                # Update or Add
                idx = next((i for i, r in enumerate(GLOBAL_AUTO_ENGINE.rules) if r['id'] == rule['id']), -1)
                if idx >= 0: GLOBAL_AUTO_ENGINE.rules[idx] = rule
                else: GLOBAL_AUTO_ENGINE.rules.append(rule)
                
                GLOBAL_AUTO_ENGINE.save_rules()
                audit_log(user['username'], "SAVE_AUTO_RULE", rule.get('name', rule['id']))
                self.write({"status": "ok", "rule": rule})

            elif action == 'delete':
                r_id = params.get('id')
                GLOBAL_AUTO_ENGINE.rules = [r for r in GLOBAL_AUTO_ENGINE.rules if r['id'] != r_id]
                GLOBAL_AUTO_ENGINE.save_rules()
                audit_log(user['username'], "DELETE_AUTO_RULE", r_id)
                self.write({"status": "ok"})
                
            elif action == 'toggle':
                r_id = params.get('id')
                rule = next((r for r in GLOBAL_AUTO_ENGINE.rules if r['id'] == r_id), None)
                if rule:
                    rule['enabled'] = not rule.get('enabled', False)
                    GLOBAL_AUTO_ENGINE.save_rules()
                    self.write({"status": "ok", "enabled": rule['enabled']})
                else: self.write({"status": "error", "error": "Rule not found"})

        except Exception as e:
            self.write({"status": "error", "error": str(e)})

class APIScheduleHandler(BaseHandler):
    async def get(self):
        if not self.get_user(): return
        target_date = self.get_argument('date', None)
        if not target_date: return self.write({"error": "Missing date"})
        
        cfg = load_config()
        resp_data = {}
        for s in cfg.get('screens', []):
            sid = s['id']
            ip = s.get('ims_ip', s['projector_ip'])
            try:
                scheds = ims_soap_client.get_schedule_list(ip, target_date)
                resp_data[sid] = {"id": sid, "name": s['name'], "schedules": scheds}
            except:
                resp_data[sid] = {"id": sid, "name": s['name'], "schedules": []}
        self.write(json.dumps(resp_data))

    async def post(self):
        user = self.get_user('Manager')
        if not user: return
        
        try:
            params = json.loads(self.request.body)
            screen_id = params.get('screen_id')
            spl_uuid = params.get('spl_uuid')
            start_time = params.get('start_time')
            
            if not screen_id or not spl_uuid or not start_time:
                return self.write(json.dumps({"status": "error", "error": "Missing required fields"}))
                
            cfg = load_config()
            screen = next((s for s in cfg['screens'] if str(s['id']) == str(screen_id)), None)
            
            if not screen:
                return self.write(json.dumps({"status": "error", "error": "Screen not found"}))
                
            host = screen.get('ims_ip', screen.get('projector_ip'))
            
            # Execute SOAP call in thread
            res = await asyncio.to_thread(ims_soap_client.create_schedule, host, spl_uuid, start_time)
            
            if res.get('status') == 'ok':
                audit_log(user['username'], "ADD_SCHEDULE", f"{screen['name']} - {spl_uuid[:8]} @ {start_time}")
                self.write(json.dumps({"status": "ok", "id": res.get('id')}))
            else:
                self.write(json.dumps({"status": "error", "error": res.get('error', 'Unknown Error')}))
                
        except Exception as e:
            self.write(json.dumps({"status": "error", "error": str(e)}))

class APITheaterPlaylistHandler(BaseHandler):
    async def get(self):
        if not self.get_user(): return
        t_id = self.get_argument('id', None)
        if not t_id: return self.write({"error": "Missing ID"})
        
        cfg = load_config()
        screen = next((s for s in cfg['screens'] if s['id'] == t_id), None)
        if not screen: return self.write({"error": "Not Found"})
        
        host = screen.get('ims_ip', screen['projector_ip'])
        status_data = THEATERS_DATA.get(t_id, {})
        spl_id = status_data.get('splId')
        items = []
        
        if spl_id:
            try: 
                if screen.get('server_type') == 'GDC':
                    user = screen.get('server_user', 'Maintenance')
                    pwd = screen.get('server_pass', DEFAULT_SERVER_PASS)
                    items = gdc_sr1000_client.get_gdc_spl_content_detailed(host, user, pwd, spl_id)
                else:
                    items = ims_soap_client.get_spl_content_detailed(host, spl_id)
                
                # Calculate precise active index based on splPosition if possible
                spl_pos = status_data.get('splPositionSec', 0)
                current_sum = 0
                calc_idx = -1
                
                for i, item in enumerate(items):
                    dur = item.get('duration', 0)
                    # If current sum <= spl_pos < current sum + duration, this is the one
                    if current_sum <= spl_pos < (current_sum + dur + 0.5): # 0.5s buffer
                        calc_idx = i
                        break
                    current_sum += dur
                
                if calc_idx != -1:
                    active_idx = calc_idx
                else:
                    active_idx = status_data.get('elementIndex', 0)

                print(f"API: Fetched {len(items)} items. Calculated Active Index: {active_idx} (based on SPL pos {spl_pos}s)")
            except Exception as e:
                print(f"API ERROR: Failed to fetch SPL content for {spl_id}: {e}")
                active_idx = status_data.get('elementIndex', 0)
        else:
            active_idx = 0
            print(f"API: No SPL loaded for theater {t_id}")

        self.write(json.dumps({
            "splId": spl_id, 
            "activeCplId": status_data.get('cplId'),
            "activeElementIndex": active_idx,
            "items": items
        }))

class APITheaterLoadHandler(BaseHandler):
    async def post(self):
        user = self.get_user('Manager')
        if not user: return
        
        t_id = self.get_argument('id', None)
        spl_uuid = self.get_argument('spl', None)
        
        if not t_id or not spl_uuid:
            return self.write(json.dumps({"status": "error", "error": "Missing ID or SPL"}))
        
        cfg = load_config()
        screen = next((s for s in cfg['screens'] if s['id'] == t_id), None)
        if not screen:
            return self.write(json.dumps({"status": "error", "error": "Screen not found"}))
        
        host = screen.get('ims_ip', screen['projector_ip'])
        
        try:
            result = await asyncio.to_thread(ims_soap_client.load_spl, host, spl_uuid)
            audit_log(user['username'], "LOAD_SPL", f"{screen['name']} - {spl_uuid[:8]}")
            self.write(json.dumps(result))
        except Exception as e:
            self.write(json.dumps({"status": "error", "error": str(e)}))

class APIControlHandler(BaseHandler):
    async def post(self):
        user = self.get_user('Manager')
        if not user: return
        params = json.loads(self.request.body)
        host = params.get('host')
        if not host and params.get('id'):
            cfg = load_config()
            screen = next((s for s in cfg['screens'] if s['id'] == params.get('id')), None)
            if screen: host = screen.get('ims_ip', screen['projector_ip'])
        
        if not host: return self.write({"status": "error", "error": "No Host"})
        
        cmd = params.get('command')
        audit_log(user['username'], f"CONTROL_{cmd}", host)
        
        if cmd == 'load_spl': res = ims_soap_client.load_spl_to_ims(host, params.get('uuid'))
        else: res = ims_soap_client.send_command(host, cmd)
        self.write(json.dumps(res))

class APIUsersHandler(BaseHandler):
    def get(self):
        if not self.get_user('Admin'): return
        users_file = os.path.join(os.path.dirname(__file__), 'users.json')
        if os.path.exists(users_file):
            with open(users_file, 'r') as f: self.write(json.dumps({'status': 'ok', 'users': json.load(f)}))
        else: self.write(json.dumps({'status': 'ok', 'users': []}))

    async def post(self):
        user = self.get_user('Admin')
        if not user: return
        params = json.loads(self.request.body)
        action = self.get_argument('action', 'add')
        users_file = os.path.join(os.path.dirname(__file__), 'users.json')
        
        users = []
        if os.path.exists(users_file):
            with open(users_file, 'r') as f: users = json.load(f)
            
        if action == 'add':
            next_id = 1
            if users:
                try: next_id = int(users[-1]['id'].split('-')[1]) + 1
                except: pass
            new_user = params; new_user['id'] = f"USR-{str(next_id).zfill(3)}"
            users.append(new_user); save_json(users_file, users)
            audit_log(user['username'], "ADD_USER", new_user['username'])
            self.write({"status": "ok", "user": new_user})
        
        elif action == 'update':
            target_id = params.get('id')
            u_idx = next((i for i, u in enumerate(users) if u['id'] == target_id), -1)
            if u_idx >= 0:
                for k in ['username', 'email', 'privilege']:
                    if k in params: users[u_idx][k] = params[k]
                if params.get('password'): users[u_idx]['password'] = params['password']
                save_json(users_file, users)
                audit_log(user['username'], "UPDATE_USER", users[u_idx]['username'])
                self.write({"status": "ok"})
            else: self.write({"status": "error"})

        elif action == 'delete':
            target_id = params.get('id')
            users = [u for u in users if u['id'] != target_id]
            save_json(users_file, users)
            audit_log(user['username'], "DELETE_USER", target_id)
            self.write({"status": "ok"})

class NoCacheStaticFileHandler(tornado.web.StaticFileHandler):
    def set_extra_headers(self, path):
        self.set_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.set_header("Pragma", "no-cache")
        self.set_header("Expires", "0")

def save_json(path, data):
    with open(path, 'w') as f: json.dump(data, f, indent=4)

class TMSWebSocket(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin): return True
    def open(self):
        WS_CLIENTS.add(self)
        # Push initial state
        self.write_message(json.dumps({"type": "status", "data": THEATERS_DATA}))
    def on_close(self): WS_CLIENTS.discard(self)

async def tms_polling_loop():
    """Background loop to poll theaters and push updates via WebSocket"""
    from pysnmp.hlapi.v3arch.asyncio import SnmpEngine
    
    await asyncio.sleep(5)  # Initial delay for server startup
    snmp_engine = SnmpEngine()
    
    while True:
        try:
            cfg = load_config()
            if not cfg:
                await asyncio.sleep(10)
                continue
                
            tasks = [poll_screen(snmp_engine, s, cfg) for s in cfg.get('screens', [])]
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Push updates to all connected WebSocket clients
            if WS_CLIENTS:
                msg = json.dumps({"type": "status", "data": THEATERS_DATA})
                for client in list(WS_CLIENTS):
                    try:
                        client.write_message(msg)
                    except:
                        WS_CLIENTS.discard(client)
            
            # Update global library every 10 minutes
            now = time.time()
            if now - LAST_LIBRARY_UPDATE[0] > 600:
                await update_global_library()
                LAST_LIBRARY_UPDATE[0] = now
                
        except Exception as e:
            print(f"Polling Loop Error: {e}")
        
        await asyncio.sleep(3)  # Poll every 3 seconds for real-time updates

def run_server():
    import subprocess
    vnc_proxy_script = os.path.join(os.path.dirname(__file__), 'vnc_proxy.py')
    if os.path.exists(vnc_proxy_script):
        print(f"INFO: Starting VNC Middleware ({vnc_proxy_script})...")
        subprocess.Popen([sys.executable, vnc_proxy_script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        print("WARNING: VNC Proxy script not found. VNC features will simply fail gracefully.")

    app = tornado.web.Application([
        (r"/api/status", APIStatusHandler),
        (r"/api/gdc/status", APIGdcStatusHandler),
        (r"/api/config", APIConfigHandler),
        (r"/api/config/add", APIConfigHandler),
        (r"/api/config/update", APIConfigHandler),
        (r"/api/config/delete", APIConfigHandler),
        (r"/api/library", APILibraryHandler),
        (r"/api/login", APILoginHandler),
        (r"/api/logout", APILogoutHandler),
        (r"/api/spl/local", APISPLHandler),
        (r"/api/spl/save", APISPLHandler),
        (r"/api/spl/delete", APISPLHandler),
        (r"/api/spl/create", APISPLCreateHandler),
        (r"/api/spl", APISPLHandler), # Fix 404
        (r"/api/spls", APISPLHandler),
        (r"/api/schedule", APIScheduleHandler),
        (r"/api/schedule/add", APIScheduleHandler),
        (r"/api/theater/playlist", APITheaterPlaylistHandler),
        (r"/api/theater/load", APITheaterLoadHandler),
        (r"/api/control", APIControlHandler),
        (r"/api/automation", APIAutomationHandler),
        (r"/api/automation/save", APIAutomationHandler),
        (r"/api/automation/delete", APIAutomationHandler),
        (r"/api/automation/toggle", APIAutomationHandler),
        (r"/api/users", APIUsersHandler),
        (r"/api/users/add", APIUsersHandler),
        (r"/api/users/update", APIUsersHandler),
        (r"/api/users/delete", APIUsersHandler),
        (r"/ws", TMSWebSocket),
        (r"/(.*)", NoCacheStaticFileHandler, {"path": FRONTEND_DIR, "default_filename": "index.html"}),
    ])

    server = tornado.httpserver.HTTPServer(app)
    server.listen(PORT, address="0.0.0.0")
    print(f"SUCCESS: TMS Portal (Real-Time) running at http://localhost:{PORT}")
    
    loop = asyncio.get_event_loop()
    loop.create_task(tms_polling_loop())
    tornado.ioloop.IOLoop.current().start()

if __name__ == "__main__":
    run_server()
