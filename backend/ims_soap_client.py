import urllib.request
import re
import time
import threading
from contextlib import contextmanager

# Configuration
IMS_PORT = 10000
USER = "manager"
PASS = "password"

# Session Cache: {host: {"id": sid, "time": timestamp}}
SESSIONS = {}
SESSION_LOCK = threading.Lock()

# Per-host locks to ensure only one SOAP session is active at a time per IMS
HOST_LOCKS = {}
HOST_LOCKS_LOCK = threading.Lock()

def get_host_lock(host):
    with HOST_LOCKS_LOCK:
        if host not in HOST_LOCKS:
            HOST_LOCKS[host] = threading.RLock()
        return HOST_LOCKS[host]

# Data Cache: {host: {type: {"data": data, "time": timestamp}}}
# Types: 'schedules', 'cpls'
DATA_CACHE = {}
CACHE_LOCK = threading.Lock()
# Persistent global cache for CPL and Schedule details to avoid thousands of SOAP calls
CPL_DETAILS_CACHE = {} 
SCHEDULE_DETAILS_CACHE = {} 
SPL_CONTENT_CACHE = {}  # Cache for SPL content (CPL list) to avoid repeated XML parsing
CACHE_TTL_LONG = 60 # Seconds for heavy data

def get_urls(host):
    base = f"http://{host}:{IMS_PORT}/dc/dcp/ws/v1"
    return {
        "session": f"{base}/SessionManagement",
        "show": f"{base}/ShowControl",
        "cpl": f"{base}/CPLManagement",
        "ingest": f"{base}/IngestManagement",
        "spl": f"{base}/SPLManagement",
        "sch": f"{base}/ScheduleManagement",
        "kdm": f"{base}/KDMManagement"
    }

def delete_spl(host, uuid):
    with soap_session(host) as sid:
        if not sid: return {"status": "error", "error": "No Session"}
        urls = get_urls(host)
        body = f"<v1:DeleteSPL><sessionId>{sid}</sessionId><splId>urn:uuid:{uuid}</splId></v1:DeleteSPL>"
        resp = _send_soap(urls["spl"], "DeleteSPL", body)
        if resp and "Fault" not in resp:
            print(f"IMS: SPL {uuid} Delete Request Sent.")
            return {"status": "ok"}
        else:
            m = re.search(r'faultstring>([^<]+)', resp or "")
            err = m.group(1) if m else "IMS Rejected Delete"
            print(f"IMS: Delete SPL Failed: {err}")
            return {"status": "error", "error": err}

def get_schedule_list(host, target_date=None):
    global DATA_CACHE, SCHEDULE_DETAILS_CACHE
    
    # Simple cache check for latest status
    if not target_date:
        with CACHE_LOCK:
            cache = DATA_CACHE.get(host, {}).get('schedules')
            if cache and (time.time() - cache["time"] < CACHE_TTL_LONG):
                return cache["data"]

    with soap_session(host) as sid:
        if not sid: return []
        urls = get_urls(host)
        
        # Optimization: Use date filters if possible (WSDL compliant)
        date_filter = ""
        if target_date:
            # target_date is YYYY-MM-DD
            start = f"{target_date}T00:00:00Z"
            end = f"{target_date}T23:59:59Z"
            date_filter = f"<dateFrom>{start}</dateFrom><dateTo>{end}</dateTo>"
        
        body = f"<v1:GetScheduleList><sessionId>{sid}</sessionId>{date_filter}</v1:GetScheduleList>"
        # WSDL says soapAction=""
        resp = _send_soap(urls["sch"], "", body)
        
        scheds = []
        if resp and "Fault" not in resp:
            ids = re.findall(r'scheduleId>(\d+)</', resp, re.IGNORECASE)
            # Only fetch what we need. If date filtered, it's already small.
            # If not filtered, take last 50 (most recent/upcoming)
            fetch_ids = ids if target_date else ids[-50:]
            
            for s_id in fetch_ids:
                # Cache lookup for static schedule info
                cache_key = f"{host}_{s_id}"
                if cache_key in SCHEDULE_DETAILS_CACHE:
                    scheds.append(SCHEDULE_DETAILS_CACHE[cache_key])
                    continue

                detail_body = f"<v1:GetScheduleInfo><sessionId>{sid}</sessionId><scheduleId>{s_id}</scheduleId></v1:GetScheduleInfo>"
                d_resp = _send_soap(urls["sch"], "", detail_body)
                if d_resp and "Fault" not in d_resp:
                    m_start = re.search(r'timeStart>([^<]+)', d_resp)
                    m_spl = re.search(r'splId>urn:uuid:([^<]+)', d_resp)
                    m_dur = re.search(r'duration>(\d+)', d_resp)
                    m_title = re.search(r'annotationText>([^<]+)', d_resp)
                    
                    spl_id = m_spl.group(1) if m_spl else "Unknown"
                    start_str = m_start.group(1) if m_start else "Unknown"
                    
                    item = {
                        "uuid": s_id,
                        "start": start_str,
                        "spl_id": spl_id,
                        "duration": int(m_dur.group(1)) if m_dur else 7200,
                        "title": m_title.group(1).strip() if m_title else f"SPL-{spl_id[:8]}"
                    }
                    scheds.append(item)
                    # Cache it (Schedules are usually static once created)
                    SCHEDULE_DETAILS_CACHE[cache_key] = item
    
    if not target_date:
        with CACHE_LOCK:
            if host not in DATA_CACHE: DATA_CACHE[host] = {}
            DATA_CACHE[host]['schedules'] = {"data": scheds, "time": time.time()}
            
    return scheds

def create_schedule(host, spl_uuid, start_time):
    with soap_session(host) as sid:
        if not sid: return {"status": "error", "error": "No Session"}
        urls = get_urls(host)
        dt = start_time
        if len(dt) == 16: dt += ":00"
        if '+' not in dt and '-' not in dt and not dt.endswith('Z'): dt += "+07:00"
        print(f"IMS ({host}): Creating Schedule for {spl_uuid} at {dt}")
        body = f"<v1:CreateSchedule><sessionId>{sid}</sessionId><scheduleInfo><splId>urn:uuid:{spl_uuid}</splId><timeStart>{dt}</timeStart></scheduleInfo></v1:CreateSchedule>"
        # Reference implementation uses empty SOAPAction
        resp = _send_soap(urls["sch"], "", body)
        
        # DEBUG: Dump to file
        try:
            with open("last_soap_resp.xml", "w", encoding="utf-8") as f:
                f.write(resp if resp else "None")
        except: pass

        if resp and "scheduleId" in resp:
            # Robust regex handles <v1:scheduleId> 123 </v1:scheduleId>
            m = re.search(r':?scheduleId>\s*(\d+)\s*</', resp)
            return {"status": "ok", "id": m.group(1) if m else "?"}
        
        # WSDL Update: CreateScheduleResponse is empty. Success = No Fault.
        if resp and "Fault" not in resp:
             print(f"IMS ({host}): Schedule Created Successfully (Empty Response).")
             return {"status": "ok", "id": "new"}
        
        # Capture Fault String if present
        if resp and "Fault" in resp:
            # Robust regex for faultstring
            fault_string = re.search(r':?faultstring>\s*(.*?)\s*</', resp, re.IGNORECASE)
            err = fault_string.group(1) if fault_string else "SOAP Fault"
            print(f"IMS Error ({host}): {err}")
            return {"status": "error", "error": err}

        print(f"DEBUG_IMS_RESP ({host}): {resp}") # LOG FULL RESPONSE
        return {"status": "error", "error": f"Invalid Response from IMS: {resp[:100] if resp else 'None'}"}

def delete_schedule(host, uuid):
    with soap_session(host) as sid:
        if not sid: return {"status": "error", "error": "No Session"}
        urls = get_urls(host)
        body = f"<v1:DeleteSchedule><sessionId>{sid}</sessionId><scheduleId>{uuid}</scheduleId></v1:DeleteSchedule>"
        resp = _send_soap(urls["sch"], "DeleteSchedule", body)
        if resp and "Fault" not in resp:
            print(f"IMS: Schedule {uuid} Delete Request Sent.")
            return {"status": "ok"}
        return {"status": "error", "error": "IMS Rejected Schedule Delete"}

# ... (rest of code)

import uuid
import datetime

def get_cpl_info(host, c_id, sid=None):
    """Fetch detailed metadata for a single CPL"""
    if sid:
        urls = get_urls(host)
        body = f"<v1:GetCPLInfo><sessionId>{sid}</sessionId><cplId>urn:uuid:{c_id}</cplId></v1:GetCPLInfo>"
        resp = _send_soap(urls["cpl"], "GetCPLInfo", body)
    else:
        with soap_session(host) as sid:
            if not sid: return None
            urls = get_urls(host)
            body = f"<v1:GetCPLInfo><sessionId>{sid}</sessionId><cplId>urn:uuid:{c_id}</cplId></v1:GetCPLInfo>"
            resp = _send_soap(urls["cpl"], "GetCPLInfo", body)
    
    if resp and "Fault" not in resp:
        # Extract metadata from the CPLInfo response
        m_title = re.search(r'(?:<|:)?(?:contentTitleText|cplTitleText|cplTitle|annotationText|title)>([^<]+)', resp, re.IGNORECASE)
        m_dur = re.search(r'(?:durationEdits|duration)>(\d+)', resp, re.IGNORECASE)
        m_kind = re.search(r'contentKind>([^<]+)', resp, re.IGNORECASE)
        m_fps = re.search(r'editRateFPS>([\d\.]+)', resp, re.IGNORECASE)
        
        # Prioritize packageSizeInBytes over cplSizeInBytes
        m_size = re.search(r'packageSizeInBytes>(\d+)', resp, re.IGNORECASE)
        if not m_size:
            m_size = re.search(r'(?:cplSizeInBytes|sizeInBytes)>(\d+)', resp, re.IGNORECASE)
        # Extract Encryption Info
        m_enc_keys = re.search(r'encryptionKeysCount>(\d+)', resp, re.IGNORECASE)
        m_width = re.search(r'pictureWidth>(\d+)', resp, re.IGNORECASE)
        m_height = re.search(r'pictureHeight>(\d+)', resp, re.IGNORECASE)
        m_is3d = re.search(r'is3D>(true|1|false|0)', resp, re.IGNORECASE)
        m_std = re.search(r'standardCompliance>([^<]+)', resp, re.IGNORECASE)
        m_audio = re.search(r'soundChannelCount>(\d+)', resp, re.IGNORECASE)
        
        # Extract Properties (Atmos, Subtitle, etc)
        props = re.findall(r'property>([^<]+)', resp, re.IGNORECASE)
        
        title = m_title.group(1).strip() if m_title else f"CPL-{c_id[:8]}"
        kind = m_kind.group(1).strip() if m_kind else "Unknown"
        fps = float(m_fps.group(1)) if m_fps else 24.0
        dur_frames = int(m_dur.group(1)) if m_dur else 0
        size_bytes = int(m_size.group(1)) if m_size else 0
        enc_count = int(m_enc_keys.group(1)) if m_enc_keys else 0
        audio_channels = int(m_audio.group(1)) if m_audio else 0
        
        # Determine 3D
        is_3d = False
        if m_is3d: is_3d = m_is3d.group(1).lower() in ["true", "1"]
        if "3D" in title.upper(): is_3d = True
        
        # Determine Resolution/Aspect (S or F)
        res_type = "?"
        if m_width and m_height:
            w = int(m_width.group(1))
            h = int(m_height.group(1))
            if h > 0:
                ratio = w / h
                if ratio > 2.0: res_type = "S"
                elif ratio > 1.5: res_type = "F"
        
        # Fallback to DCNC parsing for S/F if still unknown
        if res_type == "?":
            if "_S_" in title.upper(): res_type = "S"
            elif "_F_" in title.upper(): res_type = "F"
            elif "SCOPE" in title.upper(): res_type = "S"
            elif "FLAT" in title.upper(): res_type = "F"

        # Determine Standard (IOP or SMPTE)
        std = "SMPTE"
        if m_std: 
            raw_std = m_std.group(1).upper()
            if "INTEROP" in raw_std or "IOP" in raw_std: std = "IOP"
        elif "_IOP" in title.upper(): std = "IOP"
        elif "_SMPTE" in title.upper(): std = "SMPTE"

        # Special Attributes (Atmos, Sub)
        has_atmos = "Atmos" in props or "ATMOS" in title.upper()
        has_sub = "Subtitle" in props or "SUBS" in title.upper() or "-ID-" in title.upper()
        
        # Audio Format Label
        audio_label = ""
        if audio_channels >= 8: audio_label = "7.1"
        elif audio_channels >= 6: audio_label = "5.1"
        elif audio_channels >= 2: audio_label = "2.0"

        # Format Duration (HH:MM:SS) - Use extracted FPS
        secs = int(dur_frames / fps) if fps > 0 else 0
        h = secs // 3600; m = (secs % 3600) // 60; s = secs % 60
        dur_str = f"{h:02}:{m:02}:{s:02}"
        
        # Dynamic Size Formatting
        def format_size(b):
            if b <= 0: return "0.0 B"
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if b < 1024: return f"{b:.1f} {unit}"
                b /= 1024
            return f"{b:.1f} TB"
        
        size_str = format_size(size_bytes)
        
        # Categorize content based on ContentKind and Title (DCNC)
        category = kind.capitalize()
        if category == "Unknown":
            # Smart fallback based on title regex (Standard DCNC)
            if re.search(r'_FTR-', title): category = "Feature"
            elif re.search(r'_TLR-', title): category = "Trailer"
            elif re.search(r'_ADV-', title): category = "Advertisement"
            elif re.search(r'_TSR-', title): category = "Teaser"
            elif re.search(r'_PSA-', title): category = "Psa"
            elif re.search(r'_POL-', title): category = "Policy"
            elif re.search(r'_RTG-', title): category = "Rating"
            elif re.search(r'_TST-', title): category = "Test"
            elif re.search(r'_SHR-', title): category = "Teaser" # Short
            
        return {
            "uuid": c_id,
            "title": title,
            "duration": dur_str,
            "size": size_str,
            "kind": category,
            "fps": int(fps),
            "encrypted": enc_count > 0,
            "is3d": is_3d,
            "resolution": res_type,
            "standard": std,
            "atmos": has_atmos,
            "subtitles": has_sub,
            "audio": audio_label
        }
    return None

def get_cpl_list(host):
    global DATA_CACHE
    with CACHE_LOCK:
        cache = DATA_CACHE.get(host, {}).get('cpls')
        if cache and (time.time() - cache["time"] < CACHE_TTL_LONG):
            return cache["data"]

    with soap_session(host) as sid:
        if not sid: return []
        urls = get_urls(host)
        
        # Optimized: Use GetCPLListInfo to get all details in ONE request (Legal/Standard)
        body = f"<v1:GetCPLListInfo><sessionId>{sid}</sessionId></v1:GetCPLListInfo>"
        resp = _send_soap(urls["cpl"], "GetCPLListInfo", body)
        
        cpls = []
        if resp and "Fault" not in resp:
            # Extract info blocks
            blocks = re.findall(r'cplInfo>(.*?)</(?:[\w]+:)?cplInfo>', resp, re.DOTALL)
            for block in blocks:
                m_id = re.search(r'cplId>urn:uuid:([0-9a-fA-F\-]{36})', block, re.IGNORECASE)
                m_title = re.search(r'contentTitleText>([^<]+)', block, re.IGNORECASE)
                if not m_title:
                    m_title = re.search(r'annotationText>([^<]+)', block, re.IGNORECASE)
                m_dur = re.search(r'durationEdits>(\d+)', block, re.IGNORECASE)
                m_size = re.search(r'packageSizeInBytes>(\d+)', block, re.IGNORECASE)
                
                if m_id:
                    c_id = m_id.group(1)
                    title = m_title.group(1).strip() if m_title else f"CPL-{c_id[:8]}"
                    dur_frames = int(m_dur.group(1)) if m_dur else 0
                    size_bytes = int(m_size.group(1)) if m_size else 0
                    
                    fps = 24
                    secs = dur_frames // fps
                    h = secs // 3600; m = (secs % 3600) // 60; s = secs % 60
                    dur_str = f"{h:02}:{m:02}:{s:02}"
                    size_gb = f"{size_bytes / (1024**3):.1f} GB" if size_bytes > 0 else "0.0 GB"
                    
                    cpls.append({"uuid": c_id, "title": title, "duration": dur_str, "size": size_gb})

        # Fallback if GetCPLListInfo not supported or empty
        if not cpls:
            body_basic = f"<v1:GetCPLList><sessionId>{sid}</sessionId></v1:GetCPLList>"
            resp_basic = _send_soap(urls["cpl"], "GetCPLList", body_basic)
            if resp_basic and "Fault" not in resp_basic:
                id_list = re.findall(r'cplId>urn:uuid:([0-9a-fA-F\-]{36})', resp_basic)
                for c_id in id_list[:100]: # Safety limit for fallback
                    if c_id in CPL_DETAILS_CACHE:
                        cpls.append(CPL_DETAILS_CACHE[c_id])
                    else:
                        info = get_cpl_info(host, c_id, sid=sid)
                        if info:
                            CPL_DETAILS_CACHE[c_id] = info
                            cpls.append(info)

    with CACHE_LOCK:
        if host not in DATA_CACHE: DATA_CACHE[host] = {}
        DATA_CACHE[host]['cpls'] = {"data": cpls, "time": time.time()}
    return cpls
    with CACHE_LOCK:
        if host not in DATA_CACHE: DATA_CACHE[host] = {}
        DATA_CACHE[host]['cpls'] = {"data": cpls, "time": time.time()}
    return cpls

def get_kdm_list(host):
    """Fetch KDM status map: { cpl_uuid: 'Valid'|'Expired'|'NotYetValid' }"""
    with soap_session(host) as sid:
        if not sid: return {}
        urls = get_urls(host)
        body = f"<v1:GetKDMListInfo><sessionId>{sid}</sessionId></v1:GetKDMListInfo>"
        resp = _send_soap(urls["kdm"], "GetKDMListInfo", body)
        kdm_map = {}
        if resp and "Fault" not in resp:
            kdms = re.findall(r'kdmInfo>(.*?)</(?:[\w]+:)?kdmInfo>', resp, re.DOTALL)
            for k_xml in kdms:
                m_cpl = re.search(r'cplId>urn:uuid:([0-9a-fA-F\-]{36})', k_xml, re.IGNORECASE)
                m_val = re.search(r'keyValidity>([^<]+)', k_xml, re.IGNORECASE)
                if m_cpl and m_val:
                    cpl_id = m_cpl.group(1)
                    validity = m_val.group(1).strip()
                    if cpl_id in kdm_map:
                        if validity == "Valid": kdm_map[cpl_id] = "Valid"
                        elif validity == "NotYetValid" and kdm_map[cpl_id] != "Valid": kdm_map[cpl_id] = "NotYetValid"
                    else:
                        kdm_map[cpl_id] = validity
        return kdm_map

def load_spl(host, spl_uuid):
    """Load an SPL to the IMS server"""
    with soap_session(host) as sid:
        if not sid: return {"status": "error", "error": "No Session"}
        
        urls = get_urls(host)
        body = f"<v1:LoadShowAsset><sessionId>{sid}</sessionId><splId>urn:uuid:{spl_uuid}</splId></v1:LoadShowAsset>"
        resp = _send_soap(urls["spl"], "", body)
        
        if resp and "Fault" not in resp:
            return {"status": "ok"}
        else:
            err = "IMS Rejected Load"
            if resp:
                m = re.search(r'faultstring>([^<]+)', resp)
                if m: err = m.group(1)
            return {"status": "error", "error": err}

def create_spl(host, title, cpls):
    import base64
    from datetime import datetime
    with soap_session(host) as sid:
        if not sid: return {"status": "error", "error": f"No Session"}
        urls = get_urls(host)
        new_uuid = str(uuid.uuid4())
        now = datetime.utcnow()
        now_iso = now.strftime("%Y-%m-%dT%H:%M:%S") + f".{now.microsecond // 1000:03d}Z"
        def to_frames(dur_str):
            try:
                parts = dur_str.split(':')
                return (int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])) * 24
            except: return 240
        packs_xml = ""
        for cpl in cpls:
            c_id = cpl['uuid']; c_title = cpl.get('title', 'Unknown')
            frames = to_frames(cpl.get('duration', '00:00:10'))
            p_uuid = str(uuid.uuid4()); e_uuid = str(uuid.uuid4()); comp_uuid = str(uuid.uuid4())
            packs_xml += f"""
            <Pack>
                <Id>urn:uuid:{p_uuid}</Id>
                <EventList><Event><Id>urn:uuid:{e_uuid}</Id>
                <ElementList><MainElement><Composition>
                    <Id>urn:uuid:{comp_uuid}</Id>
                    <CompositionPlaylistId>urn:uuid:{c_id}</CompositionPlaylistId>
                    <AnnotationText>{c_title}</AnnotationText>
                    <EditRate>24 1</EditRate><EntryPoint>0</EntryPoint>
                    <Duration>{frames}</Duration><IntrinsicDuration>{frames}</IntrinsicDuration>
                </Composition></MainElement></ElementList></Event></EventList>
            </Pack>"""
        spl_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<ShowPlaylist xmlns="">
    <Id>urn:uuid:{new_uuid}</Id><ShowTitleText>{title}</ShowTitleText>
    <AnnotationText>{title}</AnnotationText><IssueDate>{now_iso}</IssueDate>
    <PackList>{packs_xml}</PackList></ShowPlaylist>"""
        b64_content = base64.b64encode(spl_xml.encode('utf-8')).decode('utf-8')
        body = f"<v1:SetSPLContent><sessionId>{sid}</sessionId><content>{b64_content}</content></v1:SetSPLContent>"
        resp = _send_soap(urls["spl"], "SetSPLContent", body)
        if resp and "Fault" not in resp: return {"status": "ok", "uuid": new_uuid}
        err = "IMS Rejected SPL"
        if resp:
            m = re.search(r'faultstring>([^<]+)', resp)
            if m: err = m.group(1)
        return {"status": "error", "error": err}

def get_ingest_list(host):
    with soap_session(host) as sid:
        if not sid: return []
        urls = get_urls(host)
        body = f"<v1:GetIngestJobs><sessionId>{sid}</sessionId></v1:GetIngestJobs>"
        _send_soap(urls["ingest"], "GetIngestJobs", body)
    return []

SPL_TITLE_CACHE = {}

def get_spl_list(host):
    with soap_session(host) as sid:
        if not sid: return []
        urls = get_urls(host)
        
        # Optimized: Use GetSPLListInfo for batch title retrieval (Legal/Standard)
        body = f"<v1:GetSPLListInfo><sessionId>{sid}</sessionId></v1:GetSPLListInfo>"
        resp = _send_soap(urls["spl"], "GetSPLListInfo", body)
        
        spls = []
        if resp and "Fault" not in resp:
            blocks = re.findall(r'splInfo>(.*?)</(?:[\w]+:)?splInfo>', resp, re.DOTALL)
            for block in blocks:
                # WSDL (SPLManagement.xsd) uses 'uuid' and 'title'
                m_id = re.search(r'(?:uuid|splId)>urn:uuid:([0-9a-fA-F\-]{36})', block, re.IGNORECASE)
                m_title = re.search(r'(?:<|:)(?:title|annotationText|showTitleText)>([^<]+)', block, re.IGNORECASE)
                if m_id:
                    s_id = m_id.group(1)
                    title = m_title.group(1).strip() if m_title else f"SPL-{s_id[:8]}"
                    spls.append({"uuid": s_id, "title": title})
                    SPL_TITLE_CACHE[s_id] = title

        # Fallback if GetSPLListInfo not supported or empty
        if not spls:
            body_basic = f"<v1:GetSPLList><sessionId>{sid}</sessionId></v1:GetSPLList>"
            resp_basic = _send_soap(urls["spl"], "GetSPLList", body_basic)
            if resp_basic and "Fault" not in resp_basic:
                ids = re.findall(r'splId>urn:uuid:([0-9a-fA-F\-]{36})', resp_basic)
                for s_id in ids[:100]:
                    spls.append({"uuid": s_id, "title": SPL_TITLE_CACHE.get(s_id, f"SPL-{s_id[:8]}")})
                    
        return spls


def load_spl_to_ims(host, uuid):
    with soap_session(host) as sid:
        if not sid: return {"status": "error", "error": "No Session"}
        urls = get_urls(host)
        
        # 1. FORCE EJECT FIRST (Doremi state safety)
        print(f"IMS ({host}): Pre-loading Eject...")
        eject_body = f"<v1:Eject><sessionId>{sid}</sessionId></v1:Eject>"
        _send_soap(urls["show"], "Eject", eject_body) # Use explicit SOAPAction
        time.sleep(1) # Allow state change

        # 2. LOAD ASSET
        print(f"IMS ({host}): Sending LoadShowAsset...")
        body = f"<v1:LoadShowAsset><sessionId>{sid}</sessionId><splId>urn:uuid:{uuid}</splId></v1:LoadShowAsset>"
        # WSDL says "" but many Doremi versions respond better to the action name or specific URI
        resp = _send_soap(urls["show"], "LoadShowAsset", body) 
        
        if resp and "Fault" not in resp: return {"status": "ok"}
        
        # Double check for empty response or HTML which we might have caught in _send_soap
        if not resp: return {"status": "error", "error": "IMS Connection Timeout"}
        
        # If Load fails, try with empty SOAPAction as fallback per WSDL
        if "Fault" in resp:
             print(f"IMS ({host}): Load with SOAPAction failed, retrying with empty action...")
             resp = _send_soap(urls["show"], "", body)
             if resp and "Fault" not in resp: return {"status": "ok"}

        err = "IMS Rejected Load"
        if resp:
            m = re.search(r'faultstring>([^<]+)', resp)
            if m: err = m.group(1)
        return {"status": "error", "error": err}

def load_spl(host, uuid):
    return load_spl_to_ims(host, uuid)


SESSION_ID = None
LOCK = threading.Lock()

def _create_envelope(body):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:v1="http://www.doremilabs.com/dc/dcp/ws/v1_0">
   <soapenv:Header/>
   <soapenv:Body>{body}</soapenv:Body>
</soapenv:Envelope>"""

import urllib.error

def _send_soap(url, action, body_content):
    raw_xml = _create_envelope(body_content)
    print(f"DEBUG SEND ({action}): {raw_xml}") # Uncomment for deep debug
    xml_data = raw_xml.encode('utf-8')
    req = urllib.request.Request(url, data=xml_data)
    req.add_header('Content-Type', 'text/xml; charset=utf-8')
    # WSDL defines soapAction="" for most operations. 
    # Reference test uses literal "" which often means the header is empty or omitted.
    # We will send it as specified, but some versions prefer the literal action name.
    # WSDL compliance: Use "" for list/status, explicit for control.
    req.add_header('SOAPAction', f'"{action}"')
    
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            resp = res.read().decode('utf-8')
            # Detect HTML error pages from Doremi (they often return 200 with error info)
            if "<html>" in resp.lower() and "error" in resp.lower():
                print(f"SOAP HTML Error ({action}): {resp[:200]}")
                return None
            return resp
    except urllib.error.HTTPError as e:
        # IMS often returns Faults as HTTP 500. We MUST read the body to see why.
        try:
            err_body = e.read().decode('utf-8')
            print(f"SOAP Fault ({action}) - HTTP {e.code}: {err_body[:500]}")
            return err_body
        except:
            print(f"SOAP HTTP Error ({action}): {e}")
            return None
    except Exception as e:
        print(f"SOAP Network Error ({action}): {e}")
        return None

def login(host):
    urls = get_urls(host)
    print(f"IMS ({host}): Attempting Login ({USER})...")
    body = f"<v1:Login><username>{USER}</username><password>{PASS}</password></v1:Login>"
    resp = _send_soap(urls["session"], "Login", body)
    
    if resp and "sessionId" in resp:
        m = re.search(r'<sessionId>(.*?)</sessionId>', resp)
        if m:
            sid = m.group(1)
            with SESSION_LOCK:
                SESSIONS[host] = {"id": sid, "time": time.time()}
            print(f"IMS ({host}): Login Success. SID={sid[:8]}...")
            return sid
    print(f"IMS ({host}): Login Failed")
    return None

def get_session(host):
    with SESSION_LOCK:
        sess = SESSIONS.get(host)
        if sess and (time.time() - sess["time"] < 300): # 5 min persistence
            return sess["id"]
    return login(host)

@contextmanager
def soap_session(host):
    """Context manager to reuse sessions and prevent 'SOAP Slow' on IMS."""
    lock = get_host_lock(host)
    with lock:
        sid = get_session(host)
        yield sid
        # We NO LONGER logout after every call to allow session persistence.
        # This resolves performance issues on Doremi server.

def logout(host):
    """Explicitly terminate the session on the IMS to free up login slots."""
    with SESSION_LOCK:
        sess = SESSIONS.pop(host, None)
    
    if sess:
        sid = sess["id"]
        urls = get_urls(host)
        print(f"IMS ({host}): Explicit Logout for SID={sid[:8]}...")
        body = f"<v1:Logout><sessionId>{sid}</sessionId></v1:Logout>"
        try:
            resp = _send_soap(urls["session"], "Logout", body)
            if resp:
                print(f"IMS ({host}): Logout Response: {resp[:100]}...")
            else:
                print(f"IMS ({host}): Logout Response: EMPTY")
        except Exception as e:
            print(f"IMS ({host}): Logout Error: {e}")
    return {"status": "ok"}

def send_command(host, cmd):
    with soap_session(host) as sid:
        if not sid: return {"status": "error", "error": "No Session"}
        urls = get_urls(host)
        if cmd == "Play": body = f"<v1:Play><sessionId>{sid}</sessionId></v1:Play>"
        elif cmd == "Pause": body = f"<v1:Pause><sessionId>{sid}</sessionId></v1:Pause>"
        elif cmd == "Stop" or cmd == "Eject": body = f"<v1:Eject><sessionId>{sid}</sessionId></v1:Eject>"
        elif cmd == "SkipForward": body = f"<v1:SkipForward><sessionId>{sid}</sessionId></v1:SkipForward>"
        elif cmd == "SkipBackward": body = f"<v1:SkipBackward><sessionId>{sid}</sessionId></v1:SkipBackward>"
        else: return {"status": "error", "error": f"Unknown Command: {cmd}"}
        
        # WSDL defines soapAction="" for these operations
        resp = _send_soap(urls["show"], "", body)
        if resp and "Fault" not in resp: return {"status": "ok"}
        return {"status": "error", "error": "IMS Rejected Command"}

def get_status_data(host):
    with soap_session(host) as sid:
        if not sid: return None
        
        urls = get_urls(host)
        body = f"<v1:GetShowStatus><sessionId>{sid}</sessionId></v1:GetShowStatus>"
        # WSDL defines soapAction="" for GetShowStatus
        resp = _send_soap(urls["show"], "", body)
        
        if resp:
            try:
                status = {"connected": True}
                
                # --- State ---
                m_state = re.search(r'(?:<|:)(?:[\w]+:)?stateInfo>([^<]+)', resp)
                val_state = m_state.group(1).strip() if m_state else "Unknown"
                if "Play" in val_state: status["playbackStatus"] = "Playing"
                elif "Pause" in val_state: status["playbackStatus"] = "Paused"
                elif "Stop" in val_state: status["playbackStatus"] = "Stopped"
                else: status["playbackStatus"] = val_state
                
                # --- SPL Title ---
                m_spl = re.search(r'<(?:[\w]+:)?splTitle>([^<]+)', resp)
                if not m_spl: m_spl = re.search(r'<(?:[\w]+:)?splTitleText>([^<]+)', resp)
                status["spl"] = m_spl.group(1).strip() if m_spl else "-"
                
                # --- Content Title ---
                m_cpl_title = re.search(r'<(?:[\w]+:)?cplTitle>([^<]+)', resp)
                if not m_cpl_title:
                    m_cpl_title = re.search(r'<(?:[\w]+:)?(?:contentTitleText|cplTitleText|annotationText)>([^<]+)', resp, re.IGNORECASE)
                
                if m_cpl_title:
                    status["content"] = m_cpl_title.group(1).strip()
                else:
                    # Fallback to CPL ID if Title missing
                    m_cpl_id = re.search(r'<(?:[\w]+:)?(?:cplId|id)>urn:uuid:([0-9a-fA-F\-]{36})', resp, re.IGNORECASE)
                    status["content"] = "-"

                # Ensure consistency
                status["cpl"] = status["content"]

                # --- SPL ID ---
                m_spl_id = re.search(r'<(?:[\w]+:)?splId>urn:uuid:([0-9a-fA-F\-]{36})', resp, re.IGNORECASE)
                status["splId"] = m_spl_id.group(1) if m_spl_id else None

                # --- CPL ID (Active) ---
                m_active_cpl = re.search(r'<(?:[\w]+:)?cplId>urn:uuid:([0-9a-fA-F\-]{36})', resp, re.IGNORECASE)
                status["cplId"] = m_active_cpl.group(1) if m_active_cpl else None

                # --- Element Index (Position in SPL) ---
                m_idx = re.search(r'<(?:[\w]+:)?(?:elementIndex|currentElementIndex)>(\d+)', resp, re.IGNORECASE)
                status["elementIndex"] = int(m_idx.group(1)) if m_idx else 0

                # --- Time Code ---
                m_pos = re.search(r'(?:<|:)(?:[\w]+:)?editPosition>(\d+)', resp)
                m_dur = re.search(r'(?:<|:)(?:[\w]+:)?editDuration>(\d+)', resp)
                m_spl_pos = re.search(r'(?:<|:)(?:[\w]+:)?splPosition>(\d+)', resp)
                m_spl_dur = re.search(r'(?:<|:)(?:[\w]+:)?splDuration>(\d+)', resp)
                
                pos_frames = int(m_pos.group(1)) if m_pos else (int(m_spl_pos.group(1)) if m_spl_pos else 0)
                dur_frames = int(m_dur.group(1)) if m_dur else (int(m_spl_dur.group(1)) if m_spl_dur else 1)
                
                # We also need splPosition specifically for calculations
                status["splPositionSec"] = int(m_spl_pos.group(1)) if m_spl_pos else 0
                
                fps = 24
                def f_to_tc(f):
                    sec = f // fps; hh = sec // 3600; mm = (sec % 3600) // 60; ss = sec % 60
                    return f"{hh:02}:{mm:02}:{ss:02}"
                
                status["position"] = f_to_tc(pos_frames)
                status["duration"] = f_to_tc(dur_frames)
                status["positionSec"] = pos_frames
                status["durationSec"] = dur_frames
                
                return status
            except Exception as e:
                return {"connected": True, "error": str(e)}
    return None

def get_spl_content_detailed(host, spl_uuid):
    """Fetch SPL content and return list of CPL metadata (uuid, title)"""
    # Check cache first
    cache_key = f"{host}:{spl_uuid}"
    if cache_key in SPL_CONTENT_CACHE:
        cached = SPL_CONTENT_CACHE[cache_key]
        if time.time() - cached["time"] < CACHE_TTL_LONG:
            return cached["data"]
    
    with soap_session(host) as sid:
        if not sid: return []
        
        urls = get_urls(host)
        body = f"<v1:GetSPLContent><sessionId>{sid}</sessionId><splId>urn:uuid:{spl_uuid}</splId></v1:GetSPLContent>"
        resp = _send_soap(urls["spl"], "", body)
        
        cpls = []
        if resp and "Fault" not in resp:
            m_b64 = re.search(r'content>([^<]+)', resp)
            if m_b64:
                import base64
                try:
                    raw_xml = base64.b64decode(m_b64.group(1)).decode('utf-8', errors='ignore')
                    
                    # 1. Iterate through Events (The actual steps in the timeline)
                    # Use namespace-agnostic search for Event
                    events = re.findall(r'<(?:[\w]+:)?Event>(.*?)</(?:[\w]+:)?Event>', raw_xml, re.DOTALL)
                    
                    if not events:
                        # Fallback: Try Compositions if no Events found
                        compositions = re.findall(r'<(?:[\w]+:)?Composition>(.*?)</(?:[\w]+:)?Composition>', raw_xml, re.DOTALL)
                        for comp_xml in compositions:
                            m_id = re.search(r'CompositionPlaylistId>(?:urn:uuid:)?([0-9a-fA-F\-]{36})', comp_xml, re.IGNORECASE)
                            m_title = re.search(r'AnnotationText>([^<]+)', comp_xml, re.IGNORECASE)
                            m_dur = re.search(r'Duration>(\d+)', comp_xml, re.IGNORECASE)
                            
                            c_id = m_id.group(1) if m_id else "unknown"
                            title = m_title.group(1).strip() if m_title else f"CPL-{c_id[:8]}"
                            
                            cat = "Unknown"
                            if "_FTR" in title.upper(): cat = "Feature"
                            elif "_TRL" in title.upper(): cat = "Trailer"
                            elif "_ADV" in title.upper(): cat = "Advertisement"
                            elif "_TSR" in title.upper(): cat = "Teaser"
                            elif "_PSA" in title.upper(): cat = "Psa"
                            elif "_POL" in title.upper() or "_POLICY" in title.upper(): cat = "Policy"
                            elif "_TST" in title.upper() or "_TEST" in title.upper(): cat = "Test"
                            elif "BLACK_MOS" in title.upper() or "BLACK MOS" in title.upper(): cat = "Policy"
                            
                            frames = int(m_dur.group(1)) if m_dur else 240
                            cpls.append({"type": "CPL", "uuid": c_id, "title": title, "category": cat, "duration": frames / 24.0})
                    else:
                        for ev_xml in events:
                            # Search for Composition inside the Event (MainElement)
                            m_comp = re.search(r'<(?:[\w]+:)?Composition>(.*?)</(?:[\w]+:)?Composition>', ev_xml, re.DOTALL)
                            
                            item = {"type": "CPL", "uuid": "unknown", "title": "Unknown", "duration": 0}
                            
                            if m_comp:
                                comp_xml = m_comp.group(1)
                                m_id = re.search(r'CompositionPlaylistId>(?:urn:uuid:)?([0-9a-fA-F\-]{36})', comp_xml, re.IGNORECASE)
                                m_title = re.search(r'AnnotationText>([^<]+)', comp_xml, re.IGNORECASE)
                                m_dur = re.search(r'Duration>(\d+)', comp_xml, re.IGNORECASE)
                                
                                c_id = m_id.group(1) if m_id else "unknown"
                                title = m_title.group(1).strip() if m_title else f"CPL-{c_id[:8]}"
                                
                                cat = "Unknown"
                                if "_FTR" in title.upper(): cat = "Feature"
                                elif "_TRL" in title.upper(): cat = "Trailer"
                                elif "_ADV" in title.upper(): cat = "Advertisement"
                                elif "_TSR" in title.upper(): cat = "Teaser"
                                elif "_PSA" in title.upper(): cat = "Psa"
                                elif "_POL" in title.upper() or "_POLICY" in title.upper(): cat = "Policy"
                                elif "_TST" in title.upper() or "_TEST" in title.upper(): cat = "Test"
                                elif "BLACK_MOS" in title.upper() or "BLACK MOS" in title.upper(): cat = "Policy"
                                
                                item["uuid"] = c_id
                                item["title"] = title
                                item["category"] = cat
                                frames = int(m_dur.group(1)) if m_dur else 240
                                item["duration"] = frames / 24.0
                            else:
                                # Might be an Automation-only Event
                                m_title = re.search(r'AnnotationText>([^<]+)', ev_xml, re.IGNORECASE)
                                item["type"] = "Other"
                                item["title"] = m_title.group(1).strip() if m_title else "[Non-CPL Step]"
                                m_dur = re.search(r'Duration>(\d+)', ev_xml, re.IGNORECASE)
                                frames = int(m_dur.group(1)) if m_dur else 0
                                item["duration"] = frames / 24.0

                            cpls.append(item)

                except Exception as e:
                    print(f"Error decoding SPL XML: {e}")

        # Cache the result
        SPL_CONTENT_CACHE[cache_key] = {"data": cpls, "time": time.time()}
        return cpls
