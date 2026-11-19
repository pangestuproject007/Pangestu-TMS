from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.request
import urllib.error
import base64
import http.cookiejar
import json
import urllib.parse
import os
import time

PORT = 8088
DEFAULT_GDC_IP = "192.168.11.63"

# Cache for GDC Session Openers to avoid multiple logins kicking users out
# Format: host -> (opener, last_login_time, username)
GDC_SESSIONS = {}

# Cache for CPL list: UUID -> Name
GDC_CPL_CACHE = {}
LAST_CPL_CACHE_TIME = 0

def get_session_opener(host):
    # Load credentials dynamically from central config.json
    username = "Maintenance"
    password = __import__("os").environ.get("TMS_DEFAULT_SERVER_PASS", "")
    config_path = "d:/Projector Monitoring/backend/config.json"
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                cfg = json.load(f)
                for screen in cfg.get("screens", []):
                    if screen.get("ims_ip") == host or screen.get("projector_ip") == host:
                        username = screen.get("server_user") or username
                        password = screen.get("server_pass") or password
                        break
        except:
            pass

    now = time.time()
    # Reuse session if exists, is less than 20 minutes old, and has the same username
    if host in GDC_SESSIONS:
        opener, last_login, saved_user = GDC_SESSIONS[host]
        if now - last_login < 1200 and saved_user == username:
            return opener

    login_url = f"http://{host}/login/Login"
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    
    auth_str = f"{username}:{password}"
    auth_b64 = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')
    
    login_req = urllib.request.Request(login_url, data=b"{}")
    login_req.add_header('Authorization', f'Basic {auth_b64}')
    login_req.add_header('Content-Type', 'application/json')
    login_req.add_header('User-Agent', 'Mozilla/5.0')
    
    with opener.open(login_req, timeout=5) as res:
        res.read()
        
    GDC_SESSIONS[host] = (opener, now, username)
    return opener

def get_sr1000_status(host):
    global LAST_CPL_CACHE_TIME
    try:
        # Get or create persistent session opener
        opener = get_session_opener(host)
            
        # Helper to query a JSON endpoint
        def query_json(path, timeout_val=5.0):
            req = urllib.request.Request(f"http://{host}{path}")
            req.add_header('User-Agent', 'Mozilla/5.0')
            with opener.open(req, timeout=timeout_val) as response:
                return json.loads(response.read().decode('utf-8'))
                
        # Query endpoints
        playback_data = query_json("/SMS/playback/get_status", 5.0)
        
        show_data = {}
        try:
            show_data = query_json("/SMS/playback/get_current_show", 5.0)
        except:
            pass
            
        os_data = {}
        try:
            os_data = query_json("/SMS/os/get_info", 5.0)
        except:
            pass
            
        tamper_data = {}
        try:
            tamper_data = query_json("/SMS/SM/tamper/get_status", 5.0)
        except:
            pass
            
        alert_data = {}
        try:
            alert_data = query_json("/SMS/Alert/list_all", 5.0)
        except:
            pass
        
        # Resolve CPL UUID
        cpl_uuid = playback_data.get("CPLUUID", "")
        cpl_name = "-"
        if cpl_uuid and cpl_uuid != "00000000-0000-0000-0000-000000000000":
            cpl_uuid_lower = cpl_uuid.lower()
            now = time.time()
            if cpl_uuid_lower in GDC_CPL_CACHE and now - LAST_CPL_CACHE_TIME < 600:
                cpl_name = GDC_CPL_CACHE[cpl_uuid_lower]
            else:
                try:
                    cpl_list_data = query_json("/SMS/CPL/list_all", 60.0)
                    cpl_list = cpl_list_data.get("CPLList", [])
                    for c in cpl_list:
                        c_uuid = c.get("UUID") or c.get("CPLUUID") or c.get("uuid")
                        if c_uuid:
                            GDC_CPL_CACHE[c_uuid.lower()] = c.get("Name") or c.get("CPLName") or c.get("title")
                    LAST_CPL_CACHE_TIME = now
                    cpl_name = GDC_CPL_CACHE.get(cpl_uuid_lower, "-")
                except:
                    # Cache failed lookup to avoid hitting the timeout repeatedly
                    GDC_CPL_CACHE[cpl_uuid_lower] = "-"
                    LAST_CPL_CACHE_TIME = now
                    cpl_name = "-"
        
        # Resolve SPL UUID
        spl_uuid = playback_data.get("SPLUUID", "")
        spl_name = "-"
        show_obj = show_data.get("Show", {})
        if show_obj and show_obj.get("SPLUUID") == spl_uuid and show_obj.get("SPLName"):
            spl_name = show_obj.get("SPLName")
        elif spl_uuid and spl_uuid != "00000000-0000-0000-0000-000000000000":
            try:
                spl_list_data = query_json("/SMS/SPL/list_all", 10.0)
                spl_list = spl_list_data.get("SPLList", [])
                for s in spl_list:
                    s_uuid = s.get("UUID") or s.get("SPLUUID") or s.get("uuid")
                    if s_uuid and spl_uuid.lower() == s_uuid.lower():
                        spl_name = s.get("Name") or s.get("SPLName") or s.get("title")
                        break
            except:
                pass
                    
        # Ambil durasi SPL secara real-time dari detail SPL
        duration_sec = 0
        if spl_uuid and spl_uuid != "00000000-0000-0000-0000-000000000000":
            try:
                spl_detail = query_json(f"/SMS/SPL/get?isSPLUUID=true&splid={spl_uuid}", 10.0)
                duration_sec = spl_detail.get("Duration", 0)
            except:
                pass
            
        # Hitung progress detik (Frame rate standard 24 fps)
        abs_frame_pos = playback_data.get("AbsFramePos", 0)
        position_sec = abs_frame_pos // 24
        
        def sec_to_tc(s):
            hh = s // 3600
            mm = (s % 3600) // 60
            ss = s % 60
            return f"{hh:02}:{mm:02}:{ss:02}"
            
        duration_tc = sec_to_tc(duration_sec)
        position_tc = sec_to_tc(position_sec)
        remaining_str = f"{position_tc} / {duration_tc}"
                    
        info_obj = os_data.get("Info", {})
        return {
            "connected": True,
            "playbackStatus": playback_data.get("State", "UNKNOWN").capitalize(),
            "spl_name": spl_name,
            "spl_uuid": spl_uuid,
            "cpl_name": cpl_name,
            "cpl_uuid": cpl_uuid,
            "duration": duration_tc,
            "remaining": remaining_str,
            "positionSec": position_sec,
            "durationSec": duration_sec,
            "system_info": {
                "model": info_obj.get("SysModel", "-"),
                "serial": info_obj.get("Serial", "-"),
                "sms_version": info_obj.get("SMSVersion", "-"),
                "screen_no": info_obj.get("ScreenNo", "-")
            },
            "security": {
                "is_divorced": tamper_data.get("isIMBDivorced", False),
                "is_door_open": tamper_data.get("isServiceDoorOpen", False)
            },
            "raw": {
                "Playback_Status": playback_data,
                "Current_Show": show_data,
                "OS_Info": os_data,
                "Tamper_Status": tamper_data,
                "Active_Alerts": alert_data
            }
        }
        
    except urllib.error.HTTPError as e:
        if e.code in [400, 401]:
            if host in GDC_SESSIONS:
                del GDC_SESSIONS[host]
            return {"connected": False, "error": "Unauthorized: Username atau password salah."}
        return {"connected": False, "error": f"HTTP Error {e.code}"}
    except Exception as e:
        if host in GDC_SESSIONS:
            del GDC_SESSIONS[host]
        return {"connected": False, "error": str(e)}

class ProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        
        if path in ["/", "/status", "/api/status", "/GetPlaystatus"]:
            query_params = urllib.parse.parse_qs(parsed_url.query)
            ip = query_params.get("ip", [DEFAULT_GDC_IP])[0]
            
            result = get_sr1000_status(ip)
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            
            response_json = json.dumps(result, indent=4)
            self.wfile.write(response_json.encode('utf-8'))
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"404 Not Found")

def run():
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, ProxyHandler)
    print(f"============================================")
    print(f"    GDC SR-1000 Proxy API Server")
    print(f"    Running at http://localhost:{PORT}")
    print(f"    Akses status: http://localhost:{PORT}/status")
    print(f"============================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping GDC Proxy Server...")
        httpd.server_close()

if __name__ == "__main__":
    run()
