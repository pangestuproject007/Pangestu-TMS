from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.request
import urllib.parse
import json
import socket
import sys
import os

# Port untuk Service Monitoring ini
PORT = 8088

# Impor driver client
import dolby_client
import gdc_client
import gdc_sr1000_client
import gdc_proxy

def is_port_open(ip, port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.5)
        s.connect((ip, port))
        s.close()
        return True
    except:
        return False

def detect_and_get_status(ip):
    # 1. Cek Dolby IMS (Port 10000)
    if is_port_open(ip, 10000):
        print(f"[DETECT] Terdeteksi DOLBY IMS pada {ip}")
        status = dolby_client.get_dolby_status(ip)
        return {
            "connected": status.get("connected", False),
            "server_type": "Dolby IMS",
            "ip": ip,
            "playback_status": status.get("playbackStatus", "Offline"),
            "spl_title": status.get("spl", "-"),
            "spl_uuid": status.get("splId", "-"),
            "cpl_title": status.get("content", "-"),
            "cpl_uuid": status.get("cplId", "-"),
            "progress": status.get("remaining", "-"),
            "raw": status
        }
        
    # 2. Cek GDC SX-3000 vs SR-1000 (Port 80)
    if is_port_open(ip, 80):
        # Coba tonton websms.fcgi (SX-3000)
        url_sx = f"http://{ip}/cgi-bin/websms.fcgi?cmd=GetPlaystatus"
        req = urllib.request.Request(url_sx)
        req.add_header('User-Agent', 'Mozilla/5.0')
        try:
            with urllib.request.urlopen(req, timeout=1.5) as response:
                if response.getcode() == 200:
                    print(f"[DETECT] Terdeteksi GDC SX-3000 pada {ip}")
                    status = gdc_client.get_gdc_status(ip)
                    return {
                        "connected": status.get("connected", False),
                        "server_type": "GDC SX-3000",
                        "ip": ip,
                        "playback_status": status.get("playbackStatus", "Offline"),
                        "spl_title": status.get("spl", "-"),
                        "spl_uuid": status.get("splId", "-"),
                        "cpl_title": status.get("content", "-"),
                        "cpl_uuid": "-",
                        "progress": status.get("remaining", "-"),
                        "raw": status
                    }
        except Exception:
            pass
            
        # Jika port 80 terbuka tapi websms.fcgi gagal/401/403, tandanya GDC SR-1000
        print(f"[DETECT] Terdeteksi GDC SR-1000 pada {ip}")
        
        # Ambil status SR-1000 dengan translate UUID lengkap dari proxy
        status = gdc_proxy.get_sr1000_status(ip)
        
        cpl_uuid = status.get("cpl_uuid", "-")
        cpl_name = status.get("cpl_name", "-")
        spl_uuid = status.get("spl_uuid", "-")
        spl_name = status.get("spl_name", "-")
        
        raw_playback = status.get("raw", {}).get("Playback_Status", {})
        pos_sec = raw_playback.get("Position", 0)
        dur_sec = raw_playback.get("Duration", 0)
        
        def sec_to_tc(s):
            hh = s // 3600
            mm = (s % 3600) // 60
            ss = s % 60
            return f"{hh:02}:{mm:02}:{ss:02}"
            
        progress_str = f"{sec_to_tc(pos_sec)} / {sec_to_tc(dur_sec)}"
            
        return {
            "connected": status.get("connected", False),
            "server_type": "GDC SR-1000",
            "ip": ip,
            "playback_status": status.get("playbackStatus", "Offline"),
            "spl_title": spl_name,
            "spl_uuid": spl_uuid,
            "cpl_title": cpl_name,
            "cpl_uuid": cpl_uuid,
            "progress": progress_str,
            "raw": status
        }
        
    return {
        "connected": False,
        "server_type": "Unknown",
        "ip": ip,
        "error": "Device unreachable or ports closed."
    }

class UnifiedServiceHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        if path in ["/", "/status", "/api/status", "/GetPlaystatus"]:
            # Dapatkan IP sasaran dari query params (?ip=...)
            params = urllib.parse.parse_qs(parsed.query)
            ip = params.get("ip", ["192.168.11.63"])[0]
            
            # Deteksi otomatis tipe IMB/IMS dan ambil datanya
            result = detect_and_get_status(ip)
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            
            self.wfile.write(json.dumps(result, indent=4).encode('utf-8'))
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"404 Not Found")

def run():
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, UnifiedServiceHandler)
    print("====================================================")
    print("   UNIFIED IMB & IMS STATUS SERVICE RUNNING")
    print(f"   Listening at http://localhost:{PORT}")
    print(f"   Akses GDC SR-1000 default  : http://localhost:{PORT}/status")
    print(f"   Akses Dolby/Doremi kustom : http://localhost:{PORT}/status?ip=192.168.100.50")
    print("====================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Unified Service...")
        httpd.server_close()

if __name__ == "__main__":
    run()
