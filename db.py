from dataclasses import dataclass
from typing import Protocol
from pathlib import Path

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
    def upsert_file(self, vault_path: Path, file: Path) -> None: ...
    def needs_indexing(self, file: Path) -> bool: ...

def is_stale(file: Path, size: int,
                    stored_ver: int, ver: int,
                    stored_chunking: str, chunking: str,
                    stored_mtime: int, mtime: int) -> bool:
    # File is empty
    if size == 0: # empty
        return False

    # Schema version changed
    # TODO might need to do some extra to wipe out old schema keys,
    # if any are ever removed!
    if stored_ver < ver:
        return True

    # Chunking changed
    if stored_chunking != chunking:
        return True
    
    # File changed
    if mtime > stored_mtime:
        return True

    return False

