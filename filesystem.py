import logging, threading, psutil
from watchfiles import watch
from pathlib import Path
from fnmatch import fnmatch
from config import Config
from db import Indexer, Feeder, WorkItem

log = logging.getLogger(__name__)

class Watcher:

    def __init__(self, cfg: Config, idx: Indexer):
        self.cfg = cfg
        self.vault_path = cfg.vault_path

        self.should_update = idx.needs_indexing
        self.upsert = idx.upsert_file
        self.delete = idx.delete_file

        self.feed = Feeder(idx)
        logging.getLogger('watchfiles').setLevel(logging.WARNING)

    def _watch(self) -> None:
        log.info(f"Starting watching dir {str(self.vault_path)}")
        for changes in watch(self.vault_path):
            paths = {path for _, path in changes} # event param is useless
            # results are an unordered set and contains multiple events
            # so we have to check ourselves to discover the final state
            for path in paths:
                self._handle_change(path)

    def _handle_change(self, path: str) -> None:
        if not fnmatch(path, self.cfg.file_match_glob):
            log.debug(f"Ignoring {path}")
            return

        path = Path(path)
        if not path.exists():
            log.info(f"Deleting from disk: {path}")
            try:
                self.delete(path)
            except Exception:
                log.exception(f"Failed to delete {path}")

            return

        # watchfiles also alerts for metadata changes so check mtime vs db
        if self.should_update(path):
            relative_path = path.relative_to(self.vault_path)
            log.info(f"Modified/new on disk: {relative_path}")
            self.feed.enqueue(WorkItem(self.vault_path, relative_path))

    def start(self):
        t = threading.Thread(target=self._watch, daemon=True)
        t.start()

def full_update(cfg:Config, idx: Indexer):
    log.info(f"Starting full refresh for {cfg.vault_path}")
    # Be nice while doing long-running work
    p = psutil.Process()
    p.ionice(psutil.IOPRIO_CLASS_IDLE)

    files = cfg.vault_path.rglob(cfg.file_match_glob)
    # exclude hidden files, or files in hidden dirs
    files = list(files)
    f = files[0]
    print(f)
    print(f.relative_to(cfg.vault_path))
    
    relative_paths = [f.relative_to(cfg.vault_path) for f in files]
    print(relative_paths[0])
    relative_paths = [f for f in relative_paths if not any(
                      part.startswith('.') for part in f.parts)]
    print(len(relative_paths))

    feed = Feeder(idx)
    for relative_path in relative_paths:
        log.debug(f"Queueing {relative_path}")
        feed.enqueue(WorkItem(cfg.vault_path, relative_path))

    # Be responsive when watching and serving queries
    p.ionice(psutil.IOPRIO_CLASS_BE)
    # probably need to use a condition to manage ionice TODO

