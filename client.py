import os, logging, socket
from config import Config

log = logging.getLogger(__name__)

def search_daemon_send(cfg: Config, query: str) -> str:
    if not os.path.exists(cfg.socket_path):
        log.error("Could not connect to nonexistent socket - is the daemon running?")
        return ''

    with socket.socket(socket.AF_UNIX) as s:
        s.connect(cfg.socket_path)
        s.sendall(query.encode())
        s.shutdown(socket.SHUT_WR)
        chunks = []
        while chunk := s.recv(4096):
            chunks.append(chunk)
        return b''.join(chunks).decode()
