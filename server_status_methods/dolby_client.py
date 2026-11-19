import urllib.request
import urllib.error
import re

IMS_PORT = 10000
USER = "manager"
PASS = "password"

def _send_soap(url, action, body_content):
    raw_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:v1="http://www.doremilabs.com/dc/dcp/ws/v1_0">
   <soapenv:Header/>
   <soapenv:Body>{body_content}</soapenv:Body>
</soapenv:Envelope>"""
    xml_data = raw_xml.encode('utf-8')
    req = urllib.request.Request(url, data=xml_data)
    req.add_header('Content-Type', 'text/xml; charset=utf-8')
    req.add_header('SOAPAction', f'"{action}"')
    
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            return res.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        try:
            return e.read().decode('utf-8')
        except:
            return None
    except Exception:
        return None

def login(host):
    url = f"http://{host}:{IMS_PORT}/dc/dcp/ws/v1/SessionManagement"
    body = f"<v1:Login><username>{USER}</username><password>{PASS}</password></v1:Login>"
    resp = _send_soap(url, "Login", body)
    if resp and "sessionId" in resp:
        m = re.search(r'<sessionId>(.*?)</sessionId>', resp)
        if m:
            return m.group(1)
    return None

def get_dolby_status(host):
    """
    Mengambil status playback, SPL, dan CPL yang sedang aktif
    pada Dolby/Doremi Server (IMS1000/2000/3000) menggunakan SOAP API port 10000.
    """
    sid = login(host)
    if not sid:
        return {
            "connected": False,
            "error": "Login Failed",
            "playbackStatus": "Offline",
            "content": "No Data"
        }
        
    url = f"http://{host}:{IMS_PORT}/dc/dcp/ws/v1/ShowControl"
    body = f"<v1:GetShowStatus><sessionId>{sid}</sessionId></v1:GetShowStatus>"
    resp = _send_soap(url, "", body)
    
    if resp:
        try:
            status = {"connected": True}
            
            # 1. State Playback
            m_state = re.search(r'stateInfo>([^<]+)', resp)
            val_state = m_state.group(1).strip() if m_state else "Unknown"
            if "Play" in val_state: status["playbackStatus"] = "Playing"
            elif "Pause" in val_state: status["playbackStatus"] = "Paused"
            elif "Stop" in val_state: status["playbackStatus"] = "Stopped"
            else: status["playbackStatus"] = val_state
            
            # 2. SPL Title
            m_spl = re.search(r'splTitle>([^<]+)', resp)
            if not m_spl: m_spl = re.search(r'splTitleText>([^<]+)', resp)
            status["spl"] = m_spl.group(1).strip() if m_spl else "-"
            
            # 3. SPL ID
            m_spl_id = re.search(r'splId>urn:uuid:([0-9a-fA-F\-]{36})', resp, re.IGNORECASE)
            status["splId"] = m_spl_id.group(1) if m_spl_id else "-"
            
            # 4. CPL / Content Title
            m_cpl_title = re.search(r'cplTitle>([^<]+)', resp)
            if not m_cpl_title:
                m_cpl_title = re.search(r'(?:contentTitleText|cplTitleText|annotationText)>([^<]+)', resp, re.IGNORECASE)
            status["content"] = m_cpl_title.group(1).strip() if m_cpl_title else "-"
            
            # 5. CPL ID
            m_cpl_id = re.search(r'cplId>urn:uuid:([0-9a-fA-F\-]{36})', resp, re.IGNORECASE)
            status["cplId"] = m_cpl_id.group(1) if m_cpl_id else "-"
            
            # 6. Progress (Frame & Waktu)
            m_pos = re.search(r'editPosition>(\d+)', resp)
            m_dur = re.search(r'editDuration>(\d+)', resp)
            
            pos_frames = int(m_pos.group(1)) if m_pos else 0
            dur_frames = int(m_dur.group(1)) if m_dur else 1
            
            fps = 24
            def frames_to_tc(f):
                sec = f // fps
                hh = sec // 3600
                mm = (sec % 3600) // 60
                ss = sec % 60
                return f"{hh:02}:{mm:02}:{ss:02}"
                
            status["duration"] = frames_to_tc(dur_frames)
            status["remaining"] = f"{frames_to_tc(pos_frames)} / {status['duration']}"
            
            return status
        except Exception as e:
            return {"connected": True, "error": str(e), "playbackStatus": "Stopped", "content": "-"}
            
    return {"connected": False, "playbackStatus": "Offline", "content": "No Data"}

if __name__ == "__main__":
    import sys
    ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.11.63"
    import json
    print(json.dumps(get_dolby_status(ip), indent=4))
