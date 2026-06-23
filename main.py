import logging, time, argparse, client
from chroma     import Chroma
from db         import Indexer
from config     import Config
from server     import Webserver, Socketserver
from filesystem import Watcher, full_update

log = logging.getLogger(__name__)

def daemon(cfg: Config, args):
    c = Chroma(cfg, cfg.vault_name)
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

def start_watcher(cfg: Config, idx: Indexer):
    w = Watcher(cfg, idx.needs_indexing, idx.upsert_file, idx.delete_file)
    w.start()


def main(args):
    cfg = Config()

    if args.search:
        client.search_daemon_send(cfg, args.search)
        return

    daemon(cfg, args)


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
# schema versioning

# main goals
# use http server locally if socket not enabled
# multiple source dirs supported (same db i guess)
# tests
# configurable from file

# stretch goals:
# db backend swappable
# preserve db entry on file move (don't delete and recreate)
# try both threading and asyncio
