import tornado.ioloop
import tornado.web
import tornado.websocket
import socket
import threading
import sys

# Minimal VNC Proxy (WebSocket to TCP)
# Requirements: pip install tornado

class VNCProxyHandler(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin):
        # Allow all origins for the proxy
        return True

    def open(self):
        self.host = self.get_argument("host", None)
        self.port = int(self.get_argument("port", 5900))
        
        if not self.host:
            print("❌ VNC Proxy: Host parameter missing.")
            self.close()
            return
            
        print(f"🔌 VNC Proxy: Connecting to {self.host}:{self.port}...")
        try:
            self.vnc_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.vnc_socket.connect((self.host, self.port))
            self.vnc_socket.setblocking(False)
            
            self.loop = tornado.ioloop.IOLoop.current()
            self.loop.add_handler(self.vnc_socket.fileno(), self.on_vnc_data, tornado.ioloop.IOLoop.READ)
            print(f"✅ VNC Proxy: Connected to {self.host}")
        except Exception as e:
            print(f"❌ VNC Proxy: Connection Failed: {e}")
            self.close()

    def on_vnc_data(self, fd, events):
        if events & tornado.ioloop.IOLoop.READ:
            try:
                data = self.vnc_socket.recv(8192)
                if data:
                    self.write_message(data, binary=True)
                else:
                    print("🔌 VNC Proxy: Socket closed by remote host.")
                    self.close()
            except Exception as e:
                print(f"❌ VNC Proxy: Read Error: {e}")
                self.close()

    def on_message(self, message):
        try:
            if isinstance(message, bytes):
                self.vnc_socket.sendall(message)
            else:
                # noVNC sometimes sends text if not configured for binary
                self.vnc_socket.sendall(message.encode())
        except Exception as e:
            print(f"❌ VNC Proxy: Write Error: {e}")
            self.close()

    def on_close(self):
        if hasattr(self, 'vnc_socket'):
            print(f"🔌 VNC Proxy: Closing connection to {self.host}")
            self.loop.remove_handler(self.vnc_socket.fileno())
            self.vnc_socket.close()

def make_app():
    return tornado.web.Application([
        (r"/vnc", VNCProxyHandler),
    ])

if __name__ == "__main__":
    port = 43730
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
        
    app = make_app()
    app.listen(port)
    print(f"🚀 VNC Proxy server running on ws://localhost:{port}/vnc")
    try:
        tornado.ioloop.IOLoop.current().start()
    except KeyboardInterrupt:
        print("\nStopping VNC Proxy...")
