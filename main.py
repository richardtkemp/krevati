import logging, time, argparse
from pathlib     import Path
from chroma      import Chroma
from db          import Indexer
from config      import Config, ConfigCreated
from server      import Webserver, Socketserver
from filesystem  import Watcher, full_update, sync_update
from misc        import upsearch_collection_name

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


def run_upsearch(cfg: Config, directory: Path, query: str | None, limit: int) -> str:
    """One-shot: (re)index a directory into its own isolated collection, then
    optionally search within it. Obeys the config for model/chunking/cache/glob,
    but retargets the vault to `directory` (NOT limited to the configured vault
    path). No daemon, no watcher — runs and exits."""
    directory = directory.resolve()
    if not directory.is_dir():
        return f"upsearch: not a directory: {directory}"

    cfg.vault_path = directory
    cfg.vault_name = upsearch_collection_name(directory)

    c = Chroma(cfg)
    n = sync_update(cfg, c)

    if not query:
        return f"Indexed {directory}: {n} file(s) (re)embedded, {c.count()} chunks total."

    results = c.search(query, n_results=limit)
    lines = [f"upsearch {directory} — {n} file(s) (re)embedded, {len(results)} match(es):"]
    for r in results:
        lines.append(f"\n[{r.score:.3f}] {r.path}\n{r.snippet[:300].strip()}")
    return "\n".join(lines)


def main(args: argparse.Namespace) -> None:
    try:
        cfg = Config()
    except ConfigCreated as e:
        log.warning(f"No config file found — wrote a starter config to {e}. "
                    f"Edit the values and run again.")
        return

    if args.upsearch:
        print(run_upsearch(cfg, Path(args.upsearch), args.search, args.limit))
        return

    if args.search:
        import client  # lazy: only the daemon-search path needs the socket client,
        print(client.search_daemon_send(cfg, args.search))  # so upsearch stays usable independently
        return

    daemon(cfg, args)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Index directory into the DB for semantic search")
    parser.add_argument('--dangerously-wipe-db', action='store_true',
                        help='Delete all indexed data before re-indexing')
    parser.add_argument('--verbose', action='store_true', help='Log verbosely')
    parser.add_argument('--search', help='Search term')
    parser.add_argument('--upsearch', metavar='DIR',
                        help='One-shot mode: upsert (changed) files under DIR into '
                             'its own isolated index, then --search within it. No daemon.')
    parser.add_argument('--limit', type=int, default=5,
                        help='Max search results (default 5)')
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
