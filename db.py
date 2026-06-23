from dataclasses import dataclass

@dataclass
class SearchResult:
    path: str
    score: float
    header: str
    snippet: str
