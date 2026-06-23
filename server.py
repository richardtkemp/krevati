import socket, os, threading, json
from flask      import Flask, request
from chroma     import Chroma
from config     import Config
from dataclasses import asdict
#from db         import SearchResult

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
            data = request.get_json(silent=True) or {}
            query = data.get('query', '')
            limit = data.get('limit', '5')
            try:
                assert isinstance(limit, int)
            except ValueError:
                return '{"error": "limit must be an int"}', 400

            if query == '':
                return '{"error": "query param must be set in request body"}', 400
            
            return json.dumps([asdict(j) for j in self.c.search(query, n_results=limit)])
    
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
        if os.path.exists(self.cfg.socket_path):
            os.unlink(self.cfg.socket_path)
        with socket.socket(socket.AF_UNIX) as s:
            s.bind(self.cfg.socket_path)
            s.listen()
            while True:
                conn, _ = s.accept()
                query = conn.recv(1024).decode()
                conn.sendall(self.pretty_print(self.c.search(query)).encode())
                conn.shutdown(socket.SHUT_WR)
                conn.close()
    
    def pretty_print(self, result) -> str:
        output = []
        for r in result:
            output.append(f"\n%%%% SCORE {r.score:.3f} %%%%\n%%%% PATH {r.path} %%%%\n%%%% HEADER {r.header} %%%%")
            output.append(r.snippet[:200])

        return '\n'.join(output)
