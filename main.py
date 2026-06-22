import logging, socket, os, time
from pathlib    import Path
from chroma     import Chroma
from config     import Config
from server     import Webserver, Socketserver

log = logging.getLogger(__name__)

def daemon(cfg: Config, args):
    c = Chroma(cfg.vaultname)
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
    from filesystem import Watcher
    w = Watcher(cfg.vaultpath, c.needs_indexing, c.upsert_file, c.delete_file)
    w.start()


def update_one(cfg: Config, file: str):
    c = Chroma(cfg.vaultname)
    log.info(f"Will check one file for updating: {file}")
    if c.needs_indexing(Path(file)):
        c.upsert_file(Path(''), Path(file))

def main(args):
    cfg = Config()

    if args.search:
        search_daemon_send(cfg, args.search)
        return

    if args.update_one:
        update_one(cfg, args.update_one)
        return

    daemon(cfg, args)


def search_daemon_send(cfg: Config, query: str) -> str:
    if not os.path.exists(cfg.socketpath):
        log.error("Could not connect to nonexistent socket - is the daemon running?")
        return ''

    with socket.socket(socket.AF_UNIX) as s:
        s.connect(cfg.socketpath)
        s.sendall(query.encode())
        s.shutdown(socket.SHUT_WR)
        chunks = []
        while chunk := s.recv(4096):
            chunks.append(chunk)
        print(b''.join(chunks).decode())

        return ''

def full_update(cfg:Config, c: Chroma):
    files = cfg.vaultpath.rglob('*.md')
    # exclude hidden files, or files in hidden dirs
    files = [f for f in files if not any(
            part.startswith('.') for part in
            f.relative_to(cfg.vaultpath).parts)]

    for file in files:
        if c.needs_indexing(file):
            c.upsert_file(cfg.vaultpath, file)

if __name__ == '__main__':
    import resource, argparse

    parser = argparse.ArgumentParser(description="Index directory into the DB for semantic search")
    parser.add_argument('--dangerously-wipe-db', action='store_true',
                        help='Delete all indexed data before re-indexing')
    parser.add_argument('--verbose', action='store_true', help='Log verbosely')
    parser.add_argument('--search', help='Search term')
    parser.add_argument('--update-one', help='Add/update one file in the db')
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level)

    resource.setrlimit(resource.RLIMIT_AS, (8 * 1024**3, 8 * 1024**3))  # 8GB virtual memory cap
    resource.setrlimit(resource.RLIMIT_CPU, (600, 600))  # 60s CPU time cap TODO

    main(args)



# NB useful collection functions
# add delete count get modify/update/upsert query 
# done!
# persistent file-watching daemon
# file type filter
# search queries to route to the daemon rather than start afresh (threading + server)

# main goals
# multiple source dirs supported (same db i guess)
# configurable
#   file type filter
#   db backend swappable
# schema versioning
# swap from socket to http for local

# stretch goals:
# preserve db entry on file move (don't delete and recreate)
# try both threading and asyncio
# try http server (what does obsidian/others actually want to use?)
