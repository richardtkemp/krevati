import logging, time, argparse, client
from chroma     import Chroma
from db         import Indexer
from config     import Config, ConfigCreated
from server     import Webserver, Socketserver
from filesystem import Watcher, full_update

log = logging.getLogger(__name__)

def daemon(cfg: Config, args: argparse.Namespace) -> None:
    c = Chroma(cfg)

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

def start_watcher(cfg: Config, idx: Indexer) -> None:
    w = Watcher(cfg, idx)
    w.start()


def main(args: argparse.Namespace) -> None:
    try:
        cfg = Config()
    except ConfigCreated as e:
        log.warning(f"No config file found — wrote a starter config to {e}. "
                    f"Edit the values and run again.")
        return

    if args.search:
        print(client.search_daemon_send(cfg, args.search))
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



# done!
# persistent file-watching daemon
# file type filter
# search queries to route to the daemon rather than start afresh (threading + server)
# added http server as well as local socket
# configurable
# schema versioning
# tests
# configurable from file
# limit num threads used by chroma/fastembed

# main goals
# use http server locally if socket not enabled
# multiple source dirs supported (same db i guess)

# stretch goals:
# db backend swappable
# preserve db entry on file move (don't delete and recreate)
# try both threading and asyncio
