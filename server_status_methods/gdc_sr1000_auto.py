import urllib.request
import urllib.error
import base64
import http.cookiejar
import json

import os

# Default fallback values
IP = "192.168.100.22"
USERNAME = "Maintenance"
PASSWORD = __import__("os").environ.get("TMS_DEFAULT_SERVER_PASS", "")

# Try to load Cinema 2 configurations from central config.json automatically
config_path = "d:/Projector Monitoring/backend/config.json"
if os.path.exists(config_path):
    try:
        with open(config_path, 'r') as f:
            cfg = json.load(f)
            # Find the GDC screen
            for screen in cfg.get("screens", []):
                if screen.get("server_type") == "GDC":
                    IP = screen.get("ims_ip") or screen.get("projector_ip") or IP
                    USERNAME = screen.get("server_user") or USERNAME
                    PASSWORD = screen.get("server_pass") or PASSWORD
                    break
    except:
        pass

def get_status():
    login_url = f"http://{IP}/login/Login"
    status_url = f"http://{IP}/SMS/playback/get_status"
    show_url = f"http://{IP}/SMS/playback/get_current_show"
    
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    
    auth_str = f"{USERNAME}:{PASSWORD}"
    auth_b64 = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')
    
    login_req = urllib.request.Request(login_url, data=b"{}")
    login_req.add_header('Authorization', f'Basic {auth_b64}')
    login_req.add_header('Content-Type', 'application/json')
    login_req.add_header('User-Agent', 'Mozilla/5.0')
    
    try:
        # 1. Login
        with opener.open(login_req, timeout=5) as res:
            res.read()
            
        # 2. Get status
        status_req = urllib.request.Request(status_url)
        status_req.add_header('User-Agent', 'Mozilla/5.0')
        with opener.open(status_req, timeout=5) as res_status:
            status_data = json.loads(res_status.read().decode('utf-8'))
            
        # 3. Get show details
        show_req = urllib.request.Request(show_url)
        show_req.add_header('User-Agent', 'Mozilla/5.0')
        spl_title = "-"
        spl_uuid = "-"
        try:
            with opener.open(show_req, timeout=5) as res_show:
                show_data = json.loads(res_show.read().decode('utf-8'))
                show_obj = show_data.get("Show", {})
                spl_title = show_obj.get("Title", "-")
                spl_uuid = show_obj.get("SPLUUID", "-")
        except:
            pass
            
        playback = status_data.get("State", "UNKNOWN")
        cpl_title = status_data.get("CPLTitle", "-")
        pos_sec = status_data.get("Position", 0)
        dur_sec = status_data.get("Duration", 0)
        
        def sec_to_tc(s):
            hh = s // 3600
            mm = (s % 3600) // 60
            ss = s % 60
            return f"{hh:02}:{mm:02}:{ss:02}"
            
        print("\n=== STATUS REALTIME GDC SR-1000 ===")
        print(f"Status Koneksi : SUCCESS")
        print(f"Status Playback : {playback.capitalize()}")
        print(f"Judul SPL       : {spl_title}")
        print(f"UUID SPL        : {spl_uuid}")
        print(f"Materi Ter-play : {cpl_title if cpl_title != '00000000-0000-0000-0000-000000000000' else 'Tidak ada materi ter-load'}")
        print(f"Progress SPL    : {sec_to_tc(pos_sec)} / {sec_to_tc(dur_sec)}")
        print("===================================\n")
        
    except urllib.error.HTTPError as e:
        print(f"[ERROR] HTTP Error {e.code}: Login gagal atau server menolak koneksi.")
    except Exception as e:
        print(f"[ERROR] Gagal terhubung ke GDC: {e}")

if __name__ == "__main__":
    get_status()
