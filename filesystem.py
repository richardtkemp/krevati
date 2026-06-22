import logging,threading
from watchfiles import watch, Change
from pathlib import Path

log = logging.getLogger(__name__)
stopwatching = threading.Event()

class Watcher:

    def __init__(self, path: Path):
        self.path = path

    def start(self):
        log.info(f"Starting watching dir {str(self.path)}")
        try:
            for changes in watch(self.path, stop_event=stopwatching):
                for event, path in changes:
                    if event == Change.added:
                        # TODO
                        log.info(f"added {path}")
                    elif event == Change.modified:
                        log.info(f"modified {path}")
                    elif event == Change.deleted:
                        log.info(f"deleted {path}")
                    else:
                        log.error(f"Unrecognised change event: {event} for path: {path}")
        except KeyboardInterrupt:
            pass
