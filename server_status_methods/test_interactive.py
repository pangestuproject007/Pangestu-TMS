import sys
import os
import json
import urllib.request
import urllib.error
import base64
import http.cookiejar
import re

# Tambahkan path lokal agar import driver berfungsi
sys.path.append(os.path.dirname(__file__))
import dolby_client
import gdc_client
import gdc_sr1000_client
import gdc_proxy

def run_gdc_sr1000(ip):
    print(f"\n[SR-1000] Menghubungkan ke GDC SR-1000 ({ip})...")
    status = gdc_proxy.get_sr1000_status(ip)
    
    if not status.get("connected"):
        print(f"[ERROR] Gagal terhubung ke SR-1000: {status.get('error', 'Unknown Error')}")
        return
        
    print("\n" + "=" * 50)
    print("      STATUS REALTIME GDC SR-1000")
    print("=" * 50)
    print(f"Status Koneksi   : SUCCESS")
    print(f"Status Playback  : {status.get('playbackStatus')}")
    print(f"Judul SPL        : {status.get('spl_name')}")
    print(f"UUID SPL         : {status.get('spl_uuid')}")
    print(f"Materi Ter-play  : {status.get('cpl_name')}")
    print(f"UUID CPL         : {status.get('cpl_uuid')}")
    print(f"Progress         : {status.get('remaining')}")
    
    sys_info = status.get("system_info", {})
    print("-" * 50)
    print(f"Model Perangkat  : {sys_info.get('model')}")
    print(f"Serial Number    : {sys_info.get('serial')}")
    print(f"Versi SMS        : {sys_info.get('sms_version')}")
    print(f"Nomor Layar      : {sys_info.get('screen_no')}")
    
    sec_info = status.get("security", {})
    print("-" * 50)
    print(f"IMB Divorced     : {sec_info.get('is_divorced')}")
    print(f"Service Door Open: {sec_info.get('is_door_open')}")
    print("=" * 50 + "\n")

def run_gdc_sx3000(ip):
    print(f"\n[SX-3000] Menghubungkan ke GDC SX-3000 ({ip})...")
    status = gdc_client.get_gdc_status(ip)
    
    if not status.get("connected"):
        print(f"[ERROR] Gagal terhubung ke SX-3000: {status.get('error', 'Unknown Error')}")
        return
        
    print("\n" + "=" * 50)
    print("      STATUS REALTIME GDC SX-3000")
    print("=" * 50)
    print(f"Status Koneksi   : SUCCESS")
    print(f"Status Playback  : {status.get('playbackStatus')}")
    print(f"Judul SPL        : {status.get('spl')}")
    print(f"UUID SPL         : {status.get('splId')}")
    print(f"Materi Ter-play  : {status.get('content')}")
    print(f"Progress SPL     : {status.get('remaining')}")
    print(f"Progress CPL     : {status.get('progress_cpl')}")
    print("=" * 50 + "\n")

def run_dolby_ims(ip):
    print(f"\n[DOLBY IMS] Menghubungkan ke Dolby IMS ({ip})...")
    status = dolby_client.get_dolby_status(ip)
    
    if not status.get("connected"):
        print(f"[ERROR] Gagal terhubung ke Dolby IMS: {status.get('error', 'Unknown Error')}")
        return
        
    print("\n" + "=" * 50)
    print("      STATUS REALTIME DOLBY IMS")
    print("=" * 50)
    print(f"Status Koneksi   : SUCCESS")
    print(f"Status Playback  : {status.get('playbackStatus')}")
    print(f"Judul SPL        : {status.get('spl')}")
    print(f"UUID SPL         : {status.get('splId')}")
    print(f"Materi Ter-play  : {status.get('content')}")
    print(f"UUID CPL         : {status.get('cplId')}")
    print(f"Progress         : {status.get('remaining')}")
    print("=" * 50 + "\n")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Penggunaan: python test_interactive.py [tipe] [ip]")
        sys.exit(1)
        
    server_type = sys.argv[1]
    server_ip = sys.argv[2]
    
    if server_type == "1":
        run_gdc_sr1000(server_ip)
    elif server_type == "2":
        run_gdc_sx3000(server_ip)
    elif server_type == "3":
        run_dolby_ims(server_ip)
    else:
        print(f"[ERROR] Tipe server '{server_type}' tidak valid.")
