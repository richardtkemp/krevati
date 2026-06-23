import logging, socket, os, time, argparse
from pathlib    import Path
from chroma     import Chroma
from config     import Config
from server     import Webserver, Socketserver
from filesystem import Watcher

log = logging.getLogger(__name__)

def daemon(cfg: Config, args):
    c = Chroma(cfg.vault_name)
    if args.dangerously_wipe_db:
        c.dangerously_wipe_db()

    full_update(cfg, c)
    start_watcher(cfg, c)

    if cfg.server_enabled:
        ws = Webserver(cfg, c)
        ws.start()
    if cfg.socket_enabled:
        ss = Socketserver(cfg, c)
        ss.start()

    while True:
        # Wait forever, let threads work
        time.sleep(1)

def start_watcher(cfg: Config, c: Chroma):
    w = Watcher(cfg, c.needs_indexing, c.upsert_file, c.delete_file)
    w.start()


def main(args):
    cfg = Config()

    if args.search:
        search_daemon_send(cfg, args.search)
        return

    daemon(cfg, args)


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
        print(b''.join(chunks).decode())

        return ''

def full_update(cfg:Config, c: Chroma):
    files = cfg.vault_path.rglob(cfg.file_match_glob)
    # exclude hidden files, or files in hidden dirs
    files = [f for f in files if not any(
            part.startswith('.') for part in
            f.relative_to(cfg.vault_path).parts)]

    for file in files:
        if c.needs_indexing(file):
            c.upsert_file(cfg.vault_path, file)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Index directory into the DB for semantic search")
    parser.add_argument('--dangerously-wipe-db', action='store_true',
                        help='Delete all indexed data before re-indexing')
    parser.add_argument('--verbose', action='store_true', help='Log verbosely')
    parser.add_argument('--search', help='Search term')
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level)

    main(args)



# NB useful collection functions
# add delete count get modify/update/upsert query 
# done!
# persistent file-watching daemon
# file type filter
# search queries to route to the daemon rather than start afresh (threading + server)
# added http server as well as local socket
# configurable

# main goals
# use http server locally if socket not enabled
# multiple source dirs supported (same db i guess)
# configurable
#   file type filter
# schema versioning

# stretch goals:
# db backend swappable
# preserve db entry on file move (don't delete and recreate)
# try both threading and asyncio
