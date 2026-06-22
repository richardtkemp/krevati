import logging, threading
from watchfiles import watch
from pathlib import Path

log = logging.getLogger(__name__)
stopwatching = threading.Event()

class Watcher:

    def __init__(self, path: Path, changechecker, upserter, deleter):
        self.path = path
        self.changechecker = changechecker
        self.upserter = upserter 
        self.deleter = deleter

    def _watch(self):
        log.info(f"Starting watching dir {str(self.path)}")
        try:
            for changes in watch(self.path, stop_event=stopwatching):
                paths = {path for _, path in changes} # event param is useless
                # results are an unordered set and contains multiple events
                # so we have to check ourselves to discover the final state
                for path in paths:
                    assert isinstance(path, str)
                    path = Path(path)
                    if path.suffix != '.md':
                        log.debug(f"ignoring {path}")
                        continue

                    if not path.exists():
                        log.info(f"deleted from disk: {path}")
                        self.deleter(path)
                        continue # don't return here, it exits the loop
    
                    # watchfiles also alerts for metadata changes so check mtime vs db
                    changed = self.changechecker(path) # changed or new!
                    if changed:
                        log.info(f"modified on disk: {path}")
                        self.upserter(path)

        except KeyboardInterrupt:
            pass

    def start(self):
        t = threading.Thread(target=self._watch, daemon=True)
        t.start()
