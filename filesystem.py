import logging, threading, os, psutil
from watchfiles import watch
from pathlib import Path
from config import Config
from chroma import Chroma

log = logging.getLogger(__name__)

class Watcher:

    def __init__(self, cfg:Config, should_update, upsert, delete):
        self.cfg = cfg
        self.vault_path = cfg.vault_path
        self.should_update = should_update
        self.upsert = upsert 
        self.delete = delete
        logging.getLogger('watchfiles').setLevel(logging.WARNING)

    def _watch(self):
        log.info(f"Starting watching dir {str(self.vault_path)}")
        for changes in watch(self.vault_path):
            paths = {path for _, path in changes} # event param is useless
            # results are an unordered set and contains multiple events
            # so we have to check ourselves to discover the final state
            for path in paths:
                assert isinstance(path, str)
                path = Path(path)
                if path.suffix != self.cfg.file_match_glob:
                    log.debug(f"Ignoring {path}")
                    continue

                if not path.exists():
                    log.info(f"Deleting from disk: {path}")
                    try:
                        self.delete(path)
                    except Exception:
                        log.exception(f"Failed to delete {path}")

                    continue # don't return here, it exits the loop

                # watchfiles also alerts for metadata changes so check mtime vs db
                if self.should_update(path):
                    log.info(f"Modified/new on disk: {path}")
                    try:
                        self.upsert(self.vault_path, path)
                    except Exception:
                        log.exception(f"Failed to upsert {path}")

    def start(self):
        t = threading.Thread(target=self._watch, daemon=True)
        t.start()

def full_update(cfg:Config, c: Chroma):
    # Be nice while doing long-running work
    os.nice(10)
    p = psutil.Process()
    p.ionice(psutil.IOPRIO_CLASS_IDLE)

    files = cfg.vault_path.rglob(cfg.file_match_glob)
    # exclude hidden files, or files in hidden dirs
    files = [f for f in files if not any(
            part.startswith('.') for part in
            f.relative_to(cfg.vault_path).parts)]

    for file in files:
        try:
            if c.needs_indexing(file):
                c.upsert_file(cfg.vault_path, file)
        except Exception:
            log.exception(f"Error indexing {file}")

    # Be responsive when watching and serving queries
    os.nice(0)
    p.ionice(psutil.IOPRIO_CLASS_BE)

