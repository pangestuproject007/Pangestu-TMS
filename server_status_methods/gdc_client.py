import urllib.request
import json

def get_gdc_status(host):
    """
    Mengambil status playback, SPL, dan CPL yang sedang aktif
    pada GDC Server (SX-3000 / SR-1000) via FastCGI API port 80.
    """
    url = f"http://{host}/cgi-bin/websms.fcgi?cmd=GetPlaystatus"
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0')
    
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            raw_data = response.read().decode('utf-8', errors='ignore')
            data = json.loads(raw_data)
            
            # Ekstraksi status playback
            playstate = data.get("playstate", "UNKNOWN")
            if playstate == "PLAYING": playstate = "Playing"
            elif playstate == "STOPPED": playstate = "Stopped"
            elif playstate == "PAUSED": playstate = "Paused"
            
            # Ekstraksi CPL / Materi aktif
            cpl_title = data.get("cpl_title", "-")
            if cpl_title == "00000000-0000-0000-0000-000000000000":
                cpl_title = "No Content Loaded"
                
            # Ekstraksi SPL aktif
            spl_info = data.get("SPLInfo", {})
            spl_title = spl_info.get("title", "-")
            spl_uuid = spl_info.get("uuid", "-")
            
            # Progress & Durasi
            pos_cpl = data.get("tc_pos_on_cpl", "00:00:00")
            dur_cpl = data.get("cpl_duration", "00:00:00")
            pos_spl = data.get("tc_pos_on_spl", "00:00:00")
            dur_spl = spl_info.get("duration", "00:00:00")
            
            return {
                "connected": True,
                "playbackStatus": playstate,
                "spl": spl_title,
                "splId": spl_uuid,
                "content": cpl_title,
                "duration": dur_spl,
                "remaining": f"{pos_spl} / {dur_spl}",
                "progress_cpl": f"{pos_cpl} / {dur_cpl}"
            }
            
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
            "playbackStatus": "Offline",
            "content": "No Data"
        }

if __name__ == "__main__":
    import sys
    ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.11.63"
    print(json.dumps(get_gdc_status(ip), indent=4))
