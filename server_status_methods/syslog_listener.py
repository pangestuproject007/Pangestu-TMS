import socket
import sys

def run_syslog_server(port=514):
    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Enable socket reuse
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        sock.bind(('0.0.0.0', port))
        print(f"==================================================")
        print(f"      SYSLOG LISTENER RUNNING ON UDP PORT {port}")
        print(f"      Mendengarkan log dari GDC IMB...")
        print(f"==================================================")
    except Exception as e:
        print(f"[ERROR] Gagal bind ke port {port}: {e}")
        if port == 514:
            print("Mencoba menggunakan port cadangan 5140...")
            run_syslog_server(5140)
        return

    while True:
        try:
            data, addr = sock.recvfrom(4096)
            message = data.decode('utf-8', errors='ignore')
            ip = addr[0]
            
            print(f"\n[{ip}:{addr[1]}] Log Diterima:")
            print(f"  {message.strip()}")
            
            # Simple parser to highlight GDC playback events
            msg_upper = message.upper()
            if "PLAY" in msg_upper or "STOP" in msg_upper or "PAUSE" in msg_upper:
                print("  --> [PLAYBACK EVENT DETECTED]")
            if "CPL" in msg_upper or "SPL" in msg_upper:
                print("  --> [CONTENT/PLAYLIST EVENT DETECTED]")
                
        except KeyboardInterrupt:
            print("\nStopping Syslog Server...")
            sock.close()
            break
        except Exception as e:
            print(f"[ERROR] {e}")

if __name__ == "__main__":
    port_to_bind = 514
    if len(sys.argv) > 1:
        try:
            port_to_bind = int(sys.argv[1])
        except:
            pass
    run_syslog_server(port_to_bind)
