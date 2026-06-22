import logging, signal
from pathlib    import Path
from chroma     import Chroma
from filesystem import Watcher,stopwatching

log = logging.getLogger(__name__)


def main(args):
    c = Chroma('vault')

    if args.dangerously_wipe_db:
        c.dangerously_wipe_db()

    if args.search:
        c.pretty_print(c.search(args.search))
        return

    signal.signal(signal.SIGTERM, lambda x,y: stopwatching.set())
    logging.getLogger('watchfiles').setLevel(logging.WARNING)
    w = Watcher(Path('/home/rich/vault'))
    w.start()

    

    ct = c.count()
    log.info(f"DONE - DB count is {ct} chunks")

def update(c: Chroma, vaultpath: Path):
    files = vaultpath.rglob('*.md')
    # exclude hidden files, or files in hidden dirs
    files = [f for f in files if not any(
            part.startswith('.') for part in
            f.relative_to(vaultpath).parts)]

    for file in files[0:12]: # TODO limit for testing
        if c.needs_indexing(file):
            c.upsert_file_to_collection(file)
        else:
            log.debug(f"already present: {file}")

if __name__ == '__main__':
    import resource, argparse

    parser = argparse.ArgumentParser(description="Index directory into the DB for semantic search")
    parser.add_argument('--dangerously-wipe-db', action='store_true',
                        help='Delete all indexed data before re-indexing')
    parser.add_argument('--verbose', action='store_true', help='Log verbosely')
    parser.add_argument('--search', help='Search term')
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level)

    resource.setrlimit(resource.RLIMIT_AS, (8 * 1024**3, 8 * 1024**3))  # 8GB virtual memory cap
    resource.setrlimit(resource.RLIMIT_CPU, (300, 300))  # 30s CPU time cap

    main(args)



# NB useful collection functions
# add delete count get modify/update/upsert query 

# main goals
# persistent file-watching daemon mode
# search queries to route to the daemon rather than start afresh
# multiple source dirs supported (same db i guess)
# configurable
# schema versioning
# db backend swappable

# stretch goals:
# preserve db entry on file move (don't delete and recreate)
