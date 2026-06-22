import socket, os, threading
from flask      import Flask, request
from chroma     import Chroma
from config     import Config

class Webserver:
    def start(self):
        t = threading.Thread(target=self._serve, daemon=True)
        t.start()

    def __init__(self, cfg: Config, c: Chroma):
        self.cfg = cfg
        self.c = c
        self.app = Flask(__name__)
    
        @self.app.before_request
        def require_auth():
            if request.remote_addr in ('127.0.0.1', '::1'):
                return # local, no auth needed
            token = request.headers.get('Authorization', '')
            if token != f'Bearer {self.cfg.API_KEY}':
                return 'Unauthorized', 401
        
        @self.app.route('/search', methods=["POST"])
        def search():
            query = request.args.get('query', '')
            try:
                limit = int(request.args.get('limit', 5))
            except ValueError:
                return '{"error": "limit must be an int"}', 400
            
            return self.c.json_print(self.c.search(query, n_results=limit))
    
    def _serve(self):
        self.app.run(host=self.cfg.host, port=self.cfg.port)
    
class Socketserver:
    def start(self):
        t = threading.Thread(target=self._serve, daemon=True)
        t.start()

    def __init__(self, cfg: Config, c: Chroma):
        self.cfg = cfg
        self.c = c

    def _serve(self):
        # Delete socket if it exists
        if os.path.exists(self.cfg.socketpath):
            os.unlink(self.cfg.socketpath)
        with socket.socket(socket.AF_UNIX) as s:
            s.bind(self.cfg.socketpath)
            s.listen()
            while True:
                conn, _ = s.accept()
                query = conn.recv(1024).decode()
                conn.sendall(self.c.pretty_print(self.c.search(query)).encode())
                conn.shutdown(socket.SHUT_WR)
                conn.close()
    
