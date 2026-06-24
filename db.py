from dataclasses import dataclass
from typing import Protocol
from pathlib import Path
import queue, threading, logging

log = logging.getLogger(__name__)

class Feeder:
    _Q: queue.Queue[WorkItem] = queue.Queue()
    _started = False
    _start_lock = threading.Lock()
    
    def __init__(self, idx: Indexer):
        self.idx = idx
        with Feeder._start_lock:
            if not Feeder._started:
                threading.Thread(target=self._worker, daemon=True, args=(idx,)).start()
                Feeder._started = True

    @staticmethod
    def _worker(idx: Indexer):
        while True:
            try:
                item = Feeder._Q.get()
                if idx.needs_indexing(item.vault_path / item.relative_path):
                    idx.upsert_file(item.vault_path, item.relative_path)
            except Exception:
                log.exception(f"Error indexing {item.relative_path}")

    def enqueue(self, item:WorkItem):
        Feeder._Q.put(item)

@dataclass
class WorkItem:
    vault_path:     Path
    relative_path:  Path

@dataclass
class SearchResult:
    path: str
    score: float
    header: str
    snippet: str

class Searcher(Protocol):
    def search(self, term: str, n_results: int = 5) -> list[SearchResult]: ...

class Indexer(Protocol):
    def dangerously_wipe_db(self) -> None: ...
    def delete_file(self, file: Path) -> None: ...
    def upsert_file(self, vault_path: Path, relative_path: Path) -> None: ...
    def needs_indexing(self, file: Path) -> bool: ...



def is_stale(file: Path, size: int,
                    stored_ver: int, ver: int,
                    stored_chunking: str, chunking: str,
                    stored_mtime: int, mtime: int) -> bool:
    # File is empty
    if size == 0: # empty
        return False

    # Schema version changed
    if stored_ver < ver:
        return True

    # Chunking changed
    if stored_chunking != chunking:
        return True
    
    # File changed
    if mtime > stored_mtime:
        return True

    return False

