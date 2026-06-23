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
