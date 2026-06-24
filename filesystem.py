import logging, threading
from watchfiles import watch
from pathlib import Path
from fnmatch import fnmatch
from config import Config
from db import Indexer, Feeder, WorkItem

log = logging.getLogger(__name__)


class PathFilter:
    """Decides whether a vault file should be skipped while indexing.

    Hidden files and files under hidden dirs are always excluded. Beyond that,
    a bare name in cfg.exclude_dirs (no '/') matches a path segment anywhere; an
    entry with a '/' is a directory subtree (absolute, or relative to the vault),
    resolved so the check still holds through symlinks and '..'.

    Built once and queried per file, so the name set / resolved subtrees are
    computed a single time.
    """

    def __init__(self, cfg: Config) -> None:
        self.vault_path = cfg.vault_path
        self.names = {e for e in cfg.exclude_dirs if '/' not in e}
        self.trees = [(cfg.vault_path / e).resolve() for e in cfg.exclude_dirs if '/' in e]

    def excludes(self, path: Path) -> bool:
        rel = path.relative_to(self.vault_path)
        if any(part.startswith('.') or part in self.names for part in rel.parts):
            return True
        # resolve only when there are subtrees to compare against
        return any(path.resolve().is_relative_to(t) for t in self.trees)


class Watcher:

    def __init__(self, cfg: Config, idx: Indexer) -> None:
        self.cfg = cfg
        self.vault_path = cfg.vault_path

        self.should_update = idx.needs_indexing
        self.upsert = idx.upsert_file
        self.delete = idx.delete_file

        self.feed = Feeder(idx)
        self.pathfilter = PathFilter(cfg)
        logging.getLogger('watchfiles').setLevel(logging.WARNING)

    def _watch(self) -> None:
        log.info(f"Starting watching dir {str(self.vault_path)}")
        for changes in watch(self.vault_path):
            paths = {path for _, path in changes} # event param is useless
            # results are an unordered set and contains multiple events
            # so we have to check ourselves to discover the final state
            for path in paths:
                self._handle_change(path)

    def _handle_change(self, path_str: str) -> None:
        if not fnmatch(path_str, self.cfg.file_match_glob):
            log.debug(f"Ignoring {path_str}")
            return

        path = Path(path_str)
        if self.pathfilter.excludes(path):
            log.debug(f"Ignoring excluded {path}")
            return

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

    def start(self) -> None:
        t = threading.Thread(target=self._watch, daemon=True)
        t.start()

def full_update(cfg:Config, idx: Indexer) -> None:
    log.info(f"Starting full refresh for {cfg.vault_path}")

    pathfilter = PathFilter(cfg)
    feed = Feeder(idx)
    for f in cfg.vault_path.rglob(cfg.file_match_glob):
        if pathfilter.excludes(f):
            continue
        relative_path = f.relative_to(cfg.vault_path)
        log.debug(f"Queueing {relative_path}")
        feed.enqueue(WorkItem(cfg.vault_path, relative_path))
