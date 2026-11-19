import urllib.request
import urllib.error
import base64
import http.cookiejar
import json
import sys
import time

# Cache for CPL list: UUID -> Name
GDC_CPL_CACHE = {}
LAST_CPL_CACHE_TIME = 0

# Cache for Session Openers to avoid logging in on every poll
# Format: host -> (opener, last_login_time, session_username)
GDC_SESSIONS = {}

def get_session_opener(host, username, password):
    now = time.time()
    # Reuse session if it exists, is less than 20 minutes old, and has the same username
    if host in GDC_SESSIONS:
        opener, last_login, saved_user = GDC_SESSIONS[host]
        if now - last_login < 1200 and saved_user == username:
            return opener
            
    # Create new session
    login_url = f"http://{host}/login/Login"
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    
    auth_str = f"{username}:{password}"
    auth_b64 = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')
    
    login_req = urllib.request.Request(login_url, data=b"{}")
    login_req.add_header('Authorization', f'Basic {auth_b64}')
    login_req.add_header('Content-Type', 'application/json')
    login_req.add_header('User-Agent', 'Mozilla/5.0')
    
    # Perform login (timeout 5s)
    with opener.open(login_req, timeout=5) as res:
        res.read()
        
    GDC_SESSIONS[host] = (opener, now, username)
    return opener

def get_sr1000_status(host, username, password):
    global LAST_CPL_CACHE_TIME
    
    try:
        # Get or create persistent session opener
        opener = get_session_opener(host, username, password)
        
        # Helper to query a JSON endpoint using the persistent session
        def query_json(path, timeout_val=5.0):
            req = urllib.request.Request(f"http://{host}{path}")
            req.add_header('User-Agent', 'Mozilla/5.0')
            with opener.open(req, timeout=timeout_val) as response:
                return json.loads(response.read().decode('utf-8'))
            
        # Query playback status
        status_data = query_json("/SMS/playback/get_status", 5.0)
            
        # Query current show details (optional, to get SPL Title/UUID)
        spl_title = "-"
        spl_uuid = status_data.get("SPLUUID", "-")
        try:
            show_data = query_json("/SMS/playback/get_current_show", 5.0)
            show_obj = show_data.get("Show", {})
            spl_title = show_obj.get("Title") or show_obj.get("SPLName") or "-"
            spl_uuid = show_obj.get("SPLUUID") or spl_uuid or "-"
        except:
            pass
            
        # Resolve CPL UUID to Name/Title using cache
        cpl_uuid = status_data.get("CPLUUID", "")
        cpl_title = "-"
        
        if cpl_uuid and cpl_uuid != "00000000-0000-0000-0000-000000000000":
            cpl_uuid_lower = cpl_uuid.lower()
            now = time.time()
            
            # Check if CPL is already cached and the cache is not expired (refresh every 10 mins)
            if cpl_uuid_lower in GDC_CPL_CACHE and now - LAST_CPL_CACHE_TIME < 600:
                cpl_title = GDC_CPL_CACHE[cpl_uuid_lower]
            else:
                # Cache miss or expired, query /SMS/CPL/list_all
                try:
                    cpl_list_data = query_json("/SMS/CPL/list_all", 60.0)
                    cpl_list = cpl_list_data.get("CPLList", [])
                    for c in cpl_list:
                        c_uuid = c.get("UUID") or c.get("CPLUUID") or c.get("uuid")
                        if c_uuid:
                            GDC_CPL_CACHE[c_uuid.lower()] = c.get("Name") or c.get("CPLName") or c.get("title")
                    LAST_CPL_CACHE_TIME = now
                    cpl_title = GDC_CPL_CACHE.get(cpl_uuid_lower, "-")
                except Exception as e:
                    # In case of timeout or error, cache fallback value to avoid repeating timeouts
                    GDC_CPL_CACHE[cpl_uuid_lower] = "-"
                    LAST_CPL_CACHE_TIME = now
                    cpl_title = "-"
        
        # Ambil durasi SPL secara real-time dari detail SPL
        duration_sec = 0
        if spl_uuid and spl_uuid != "00000000-0000-0000-0000-000000000000":
            try:
                spl_detail = query_json(f"/SMS/SPL/get?isSPLUUID=true&splid={spl_uuid}", 10.0)
                duration_sec = spl_detail.get("Duration", 0)
            except:
                pass
                
        # Hitung progress detik (Frame rate standard 24 fps)
        abs_frame_pos = status_data.get("AbsFramePos", 0)
        position_sec = abs_frame_pos // 24
        
        def sec_to_tc(s):
            hh = s // 3600
            mm = (s % 3600) // 60
            ss = s % 60
            return f"{hh:02}:{mm:02}:{ss:02}"
            
        duration_tc = sec_to_tc(duration_sec)
        position_tc = sec_to_tc(position_sec)
        remaining_str = f"{position_tc} / {duration_tc}"
            
        return {
            "connected": True,
            "playbackStatus": status_data.get("State", "UNKNOWN").capitalize(),
            "spl": spl_title,
            "splId": spl_uuid,
            "content": cpl_title,
            "cplId": cpl_uuid,
            "duration": duration_tc,
            "remaining": remaining_str,
            "positionSec": position_sec,
            "durationSec": duration_sec,
            "splPositionSec": position_sec
        }
        
    except urllib.error.HTTPError as e:
        # Clear session on auth error to force relogin next time
        if e.code in [400, 401]:
            if host in GDC_SESSIONS:
                del GDC_SESSIONS[host]
            return {"connected": False, "error": "Unauthorized: Username atau password salah."}
        return {"connected": False, "error": f"HTTP Error {e.code}"}
    except Exception as e:
        # Clear session on connection/timeout error to force relogin next time
        if host in GDC_SESSIONS:
            del GDC_SESSIONS[host]
        return {"connected": False, "error": str(e)}

def get_gdc_spl_list(host, username, password):
    try:
        opener = get_session_opener(host, username, password)
        list_url = f"http://{host}/SMS/SPL/list_all"
        
        list_req = urllib.request.Request(list_url)
        list_req.add_header('User-Agent', 'Mozilla/5.0')
        with opener.open(list_req, timeout=15.0) as res_list:
            list_data = json.loads(res_list.read().decode('utf-8'))
            
        spl_list = list_data.get("SPLList", [])
        result = []
        for s in spl_list:
            uuid = s.get("UUID") or s.get("SPLUUID") or s.get("uuid")
            title = s.get("Name") or s.get("SPLName") or s.get("title") or f"SPL-{uuid[:8]}"
            result.append({"uuid": uuid, "title": title})
        return result
    except Exception as e:
        print(f"Error GDC get_gdc_spl_list: {e}")
        if host in GDC_SESSIONS:
            del GDC_SESSIONS[host]
        return []

def get_gdc_spl_content_detailed(host, username, password, spl_uuid):
    try:
        opener = get_session_opener(host, username, password)
        detail_url = f"http://{host}/SMS/SPL/get?isSPLUUID=true&splid={spl_uuid}"
        
        detail_req = urllib.request.Request(detail_url)
        detail_req.add_header('User-Agent', 'Mozilla/5.0')
        with opener.open(detail_req, timeout=15.0) as res_detail:
            spl_data = json.loads(res_detail.read().decode('utf-8'))
            
        show_playlist = spl_data.get("ShowPlaylist", spl_data)
        pack_list_obj = show_playlist.get("PackList", {})
        packs = pack_list_obj.get("Pack", [])
        if isinstance(packs, dict):
            packs = [packs]
            
        cpls = []
        for pack in packs:
            event_list_obj = pack.get("EventList", {})
            events = event_list_obj.get("Event", [])
            if isinstance(events, dict):
                events = [events]
                
            for event in events:
                element_list = event.get("ElementList", {})
                main_element = element_list.get("MainElement", {})
                composition = main_element.get("Composition", {})
                
                if composition:
                    cpl_id_urn = composition.get("CompositionPlaylistId", "")
                    cpl_id = cpl_id_urn.replace("urn:uuid:", "")
                    title = composition.get("AnnotationText", f"CPL-{cpl_id[:8]}")
                    
                    dur_frames = composition.get("IntrinsicDuration") or composition.get("Duration") or 240
                    try:
                        dur_frames = int(dur_frames)
                    except:
                        dur_frames = 240
                        
                    duration_sec = dur_frames / 24.0
                    
                    cat = "Unknown"
                    title_upper = title.upper()
                    if "_FTR" in title_upper: cat = "Feature"
                    elif "_TRL" in title_upper or "_TLR" in title_upper: cat = "Trailer"
                    elif "_ADV" in title_upper: cat = "Advertisement"
                    elif "_TSR" in title_upper: cat = "Teaser"
                    elif "_PSA" in title_upper: cat = "Psa"
                    elif "_POL" in title_upper: cat = "Policy"
                    elif "_TST" in title_upper or "_TEST" in title_upper: cat = "Test"
                    
                    cpls.append({
                        "type": "CPL",
                        "uuid": cpl_id,
                        "title": title,
                        "category": cat,
                        "duration": duration_sec
                    })
        return cpls
    except Exception as e:
        print(f"Error GDC get_gdc_spl_content_detailed: {e}")
        if host in GDC_SESSIONS:
            del GDC_SESSIONS[host]
        return []

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Penggunaan: python gdc_sr1000_client.py [IP] [USERNAME] [PASSWORD]")
        print("Contoh: python gdc_sr1000_client.py 192.168.100.22 Technician <PASSWORD>")
        sys.exit(1)
        
    host = sys.argv[1]
    user = sys.argv[2]
    pwd = sys.argv[3]
    
    res = get_sr1000_status(host, user, pwd)
    print(json.dumps(res, indent=4))
